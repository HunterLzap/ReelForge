"""Plan edits against a snapshot, then publish once under its revision lock."""

import asyncio
import base64
import re
from io import BytesIO

from fastapi import HTTPException
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from app.core.auth import project_dir, resolve_safe_path
from app.schemas.director import Turn
from app.schemas.review_pin import ReviewPin
from app.schemas.timeline import (
    TimelineDocument,
    TimelineOp,
    TimelinePatchRequest,
    Track,
)
from app.services import pin_service
from app.services.director_chat import skill_for
from app.services.model_router import router
from app.services.timeline_engine import RevisionConflict, engine


class ChatEdit(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    current_time_ms: int = Field(0, ge=0)
    selected_track: Track | None = None
    selected_clip_id: str | None = None
    base_revision: int = Field(ge=0)
    history: list[Turn] = Field(default_factory=list, max_length=50)


class EditPlan(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    ops: list[TimelineOp] = Field(min_length=1)


class EditResult(EditPlan):
    timeline: TimelineDocument
    previous_revision: int
    applied_revision: int


class PinFixResult(EditResult):
    pin: ReviewPin


def frame_image(pin):
    path = resolve_safe_path(project_dir(pin.project_id), pin.frame_path)
    if not path.is_file():
        raise HTTPException(404, "找不到批注截帧")
    with Image.open(path) as image, BytesIO() as preview:
        image.thumbnail((1280, 1280))
        image.convert("RGB").save(preview, format="JPEG")
        return base64.b64encode(preview.getvalue()).decode("ascii")


def replacement(message, old):
    quoted = re.findall(r'[「“"]([^」”"]+)[」”"]', message)
    if quoted:
        return quoted[-1]
    explicit = re.search(
        r"(?:改[成为]|换[成为]|替换[成为]|改字[：:]|改[为成]?\s*[：:])\s*(.+)", message
    )
    if explicit:
        return explicit[1].strip()
    if re.search(r"简洁|精简|简短|缩写|shorter|concise", message, re.IGNORECASE):
        shorter = re.sub(
            r"^(?:接下来|然后|那么|我们先|我们|现在|请大家|请)\s*[，,]?\s*", "", old
        )
        shorter = re.split(r"[，,。；;]", shorter, maxsplit=1)[0]
        if shorter and shorter != old:
            return shorter
    raise HTTPException(422, "请给出替换文字，或选中需要精简的长句")


def offline_plan(message, time_ms, track, selected, active, bbox):
    def target(name):
        if selected and selected[0] == name:
            return selected[1]
        return next(iter(active[name]), None)

    def update(name, clip, fields, summary):
        return {
            "summary": summary,
            "ops": [
                {
                    "op": "update_clip",
                    "track": name,
                    "clip_id": clip.id,
                    "patch": fields,
                }
            ],
        }

    # Replacement copy may itself contain words such as “放大” or “缩短”.
    intent = re.split(r'改[成为]|换[成为]|替换[成为]|[「“"]', message, maxsplit=1)[0]
    if re.search(r"缩短|延长|裁剪|剪短|trim|extend|shorten", intent, re.IGNORECASE):
        match = re.search(
            r"(缩短|延长|裁剪|剪短|trim|extend|shorten)\s*(到|至|为|by|to)?\s*(\d+(?:\.\d+)?)\s*(毫秒|ms|秒|s)",
            message,
            re.IGNORECASE,
        )
        name = selected[0] if selected else track or "video"
        clip = target(name)
        if not clip:
            raise HTTPException(422, "此处没有可调整时长的片段")
        duration = clip.end_ms - clip.start_ms
        delta = (
            round(float(match[3]) * (1 if match[4] in {"ms", "毫秒"} else 1000))
            if match
            else min(500, max(1, duration // 4))
        )
        if match and match[2] in {"到", "至", "为", "to"}:
            duration = delta
        else:
            duration += (
                delta if re.search("延长|extend", message, re.IGNORECASE) else -delta
            )
        if duration <= 0:
            raise HTTPException(422, "调整后的片段时长必须大于零")
        fields = {"end_ms": clip.start_ms + duration}
        if clip.source_out_ms is not None:
            fields["source_out_ms"] = clip.source_in_ms + round(duration * clip.speed)
        return update(name, clip, fields, f"将片段时长调整为 {duration} ms")

    if re.search(
        r"zoom|focus|spotlight|放大|高亮|对齐|聚焦|特写|聚光", intent, re.IGNORECASE
    ):
        clip = target("annotation")
        kind = (
            "spotlight"
            if re.search("高亮|聚光|spotlight", message, re.IGNORECASE)
            else "zoom_focus"
        )
        box = bbox or (getattr(clip, "target_bbox", None) if clip else None)
        fields = {
            "kind": kind,
            "target_bbox": box or {"x": 0.3, "y": 0.3, "w": 0.4, "h": 0.4},
            "scale": 1.65,
            "spotlight": kind == "spotlight",
        }
        if clip and clip.kind in {"spotlight", "zoom_focus"}:
            return update("annotation", clip, fields, "调整画面标注的聚焦区域")
        end = min([c.end_ms for c in active["video"]] + [time_ms + 2000])
        return {
            "summary": f"在 {time_ms / 1000:g} 秒处添加画面聚焦标注",
            "ops": [
                {
                    "op": "add_clip",
                    "track": "annotation",
                    "clip": dict(fields, start_ms=time_ms, end_ms=end),
                }
            ],
        }

    if re.search(
        r"改字|文案|标题|字幕|改成|改为|精简|caption|title|subtitle",
        message,
        re.IGNORECASE,
    ):
        sub = target("subtitle")
        card_track = (
            selected[0] if selected and selected[1].kind == "motion_card" else "video"
        )
        card = target(card_track)
        wants_subtitle = re.search("字幕|caption|subtitle", intent, re.IGNORECASE)
        wants_title = re.search("标题|title", intent, re.IGNORECASE)
        use_subtitle = wants_subtitle or (
            not wants_title
            and (
                track == "subtitle"
                or not selected
                and track != "video"
                or not card
                or card.kind != "motion_card"
            )
        )
        if use_subtitle and sub:
            return update(
                "subtitle",
                sub,
                {"text": replacement(message, getattr(sub, "text", ""))},
                "更新当前字幕文字",
            )
        if wants_subtitle and not sub:
            raise HTTPException(422, "此处没有可编辑的字幕")
        if card and card.kind == "motion_card":
            props = getattr(card, "props", {})
            key = next(
                (key for key in ("title", "heading", "quote") if key in props), "title"
            )
            return update(
                card_track,
                card,
                {"props": {key: replacement(message, props.get(key, ""))}},
                "更新动效卡文案",
            )
    raise HTTPException(422, "请指定需要修改的片段、文字、时长或聚焦区域")


async def apply_edit(pid, body, *, pin=None, author="internal_ai"):
    doc = await engine.get(pid)
    if doc.revision != body.base_revision:
        raise RevisionConflict(doc.revision)
    time_ms = body.current_time_ms
    at = re.search(
        r"(?:在|第|at\s+)\s*(\d+(?:\.\d+)?)\s*(毫秒|ms|秒|s)",
        body.message,
        re.IGNORECASE,
    )
    if at and pin is None:
        time_ms = round(float(at[1]) * (1 if at[2] in {"ms", "毫秒"} else 1000))
    active = {}
    selected = None
    for name in type(doc.tracks).model_fields:
        clips = getattr(doc.tracks, name)
        active[name] = [c for c in clips if c.start_ms <= time_ms < c.end_ms]
        if not body.selected_track or name == body.selected_track:
            for clip in clips:
                if clip.id == body.selected_clip_id:
                    selected = name, clip
    if body.selected_clip_id and selected is None:
        raise HTTPException(409, "目标片段已不存在，请重新选择")
    bbox = pin.bbox.model_dump() if pin and pin.bbox else None
    evidence = {
        "message": body.message,
        "history": [turn.model_dump() for turn in body.history],
        "time_ms": time_ms,
        "selected_track": body.selected_track,
        "selected_clip": selected[1].model_dump() if selected else None,
        "overlapping": {
            name: [c.model_dump() for c in clips] for name, clips in active.items()
        },
        "skill": skill_for(doc.skill_id).guide,
        "aspect_ratio": doc.aspect_ratio,
    }
    if pin:
        evidence["pin"] = pin.model_dump()
        vision = await router.complete_json(
            "vlm_vision",
            "描述批注截帧中目标框的位置和相关画面文字。",
            evidence,
            lambda: {"bbox": bbox, "time_ms": time_ms},
            image=await asyncio.to_thread(frame_image, pin),
        )
        if vision.get("provider") == "mcp":
            raise HTTPException(409, vision)
        evidence["frame_description"] = vision
    data = await router.complete_json(
        "llm_director",
        "根据 message 与当前 Skill 精准修改选中片段或时间点。保留无关内容，返回中文摘要 summary 和原子操作 ops。"
        "框选标注用 target_bbox，字幕用 text，动效卡用 props；开始与结束时间为 start_ms 和 end_ms。",
        {**evidence, "response_schema": EditPlan.model_json_schema()},
        lambda: offline_plan(
            body.message, time_ms, body.selected_track, selected, active, bbox
        ),
    )
    if data.get("provider") == "mcp":
        raise HTTPException(409, data)
    try:
        plan = EditPlan.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(502, "模型返回了无效的时间轴修改") from exc
    patch = TimelinePatchRequest(
        base_revision=doc.revision,
        author=author,
        review_pin_id=pin.id if pin else None,
        **plan.model_dump(),
    )
    after = await engine.patch(pid, patch, resolve_pin=pin)
    result = dict(
        timeline=after,
        previous_revision=doc.revision,
        applied_revision=after.revision,
        **plan.model_dump(),
    )
    if pin:
        result["pin"] = pin.model_copy(
            update={
                "status": "resolved",
                "resolved_by_revision": after.revision,
                "resolution_summary": plan.summary,
            }
        )
    return result


async def fix_pin(pid, pin_id, base_revision=None, author="internal_ai"):
    pin = await pin_service.lookup(pid, pin_id)
    if pin.status != "open":
        raise HTTPException(409, "只能修复待处理的批注")
    body = ChatEdit(
        message=pin.note,
        current_time_ms=pin.time_ms,
        selected_track=pin.track,
        selected_clip_id=pin.clip_id,
        base_revision=base_revision
        if base_revision is not None
        else (await engine.get(pid)).revision,
    )
    return await apply_edit(pid, body, pin=pin, author=author)
