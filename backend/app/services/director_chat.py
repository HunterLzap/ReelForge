import asyncio
import hashlib
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from aiohttp import ClientError
from fastapi import HTTPException
from jsonschema import Draft202012Validator
from openai import OpenAIError
from pydantic import BaseModel, ValidationError

from app.core.auth import project_dir, resolve_safe_path
from app.db import repository as repo
from app.media import tts
from app.media.limits import project_files
from app.schemas.director import Plan, Shot
from app.schemas.timeline import TimelinePatchRequest
from app.services import asset_indexer, web_sourcing
from app.services.model_router import router
from app.services.skill_registry import get_skill
from app.services.timeline_engine import RevisionConflict, engine


class Intent(Shot):
    allow_web: bool = True


class Outline(BaseModel):
    reply: str
    shots: list[Intent]


def skill_for(skill_id):
    try:
        return get_skill(skill_id)
    except KeyError as exc:
        raise HTTPException(422, "未知编导 Skill") from exc


def relevance(query, name):
    q, n = query.casefold(), Path(name).stem.casefold()
    if not q or not n:
        return 0
    if q in n or n in q:
        return 100 + min(len(q), len(n))
    words = re.findall(r"[a-z0-9]{2,}|[\u3400-\u9fff]+", n)
    score = 0
    for word in words:
        if len(word) >= 2 and word in q:
            score += len(word)
        elif re.search(r"[\u3400-\u9fff]", word):
            score += sum(word[i : i + 2] in q for i in range(len(word) - 1))
    return score


def offline_outline(body, names):
    previous = [turn.content for turn in body.history if turn.role == "user"]
    topic = (previous[0] if previous else body.message)[:90]
    direction = body.message[:90]
    brief = topic + " " + direction
    matches = sorted(names, key=lambda n: relevance(brief, n), reverse=True)
    query = (
        Path(matches[0]).stem
        if matches and relevance(brief, matches[0]) >= 2
        else topic
    )
    chapter = "chapter_card" if body.skill_id == "ai-news-montage" else "cover"
    faster = any(w in direction for w in ("短", "快", "紧凑"))

    if any(word in topic.casefold() for word in ("模型", "ai", "model")):
        question, explanation, requested = (
            "更新了什么",
            "从能力、使用条件和评测方法三个角度看这次更新。",
            "模型推理过程",
        )
    elif any(word in topic.casefold() for word in ("产品", "功能", "product")):
        question, explanation, requested = (
            "使用场景",
            "从一次完整操作看这个功能解决了哪一步。",
            "产品功能操作",
        )
    else:
        question, explanation, requested = (
            "原理拆解",
            "把问题拆成输入、过程和结果，逐步核对。",
            "原理验证过程",
        )

    def scene(title, narration, query, seconds, component=None, web=False):
        return {
            "title": title,
            "narration": narration,
            "visual_query": query,
            "duration_ms": round(seconds * (800 if faster else 1000)),
            "component_id": component,
            "allow_web": web,
        }

    outline = {
        "reply": f"围绕「{topic}」安排了开场、公开资料、解读和实拍四幕。"
        + (f"本轮按「{direction}」调整。" if previous else ""),
        "shots": [
            scene(topic, f"今天聚焦{topic}。", query, 3, chapter, True),
            scene(
                "公开资料",
                f"从公开资料看{topic}的背景。",
                topic + " 公开资料",
                4,
                None,
                True,
            ),
            scene(question, explanation, "章节要点梳理", 3, chapter),
            scene(
                "现场验证",
                "用现场画面核对实际表现。",
                topic + " 独家现场实拍 " + requested,
                4,
            ),
        ],
    }

    for i, shot in enumerate(outline["shots"], 1):
        shot["id"] = f"shot_{i}"
    return outline


async def chat(pid, body):
    doc = await engine.get(pid)
    skill = skill_for(body.skill_id)
    try:
        library = [x for x in await asset_indexer.search() if x.kind != "audio"]
    except HTTPException:
        library = []
    project = [x for x in await repo.media_assets(pid) if playable_media(pid, x)]
    names = [x.filename for x in library] + [x["filename"] for x in project]
    evidence = {
        "message": body.message,
        "history": [t.model_dump() for t in body.history],
        "aspect": body.aspect_ratio,
        "skill": skill.guide,
        "assets": names[:120],
        "templates": [t.id for t in skill.templates],
        "descriptions": [
            {"filename": a.filename, "caption": a.caption, "tags": a.tags}
            for a in library[:80]
        ],
    }
    data = await router.complete_json(
        "llm_director",
        "根据对话及分镜 Skill 编导短片。返回 reply 和 shots 数组，每幕含 title,narration,visual_query,duration_ms,allow_web。"
        "选中本地素材时 visual_query 使用已有文件名（去扩展名）或对应标签。需要专属实拍时 allow_web=false。适于动效的镜头可给 component_id 与 props；具体实物拍摄缺料应留空。",
        evidence,
        lambda: offline_outline(body, names),
    )
    if data.get("provider") == "mcp":
        return {
            "reply": "等待外部 MCP 编导返回分镜",
            "shots": [],
            "passthrough": data,
            "base_revision": doc.revision,
        }
    try:
        outline = Outline.model_validate(data)
        if not 1 <= len(outline.shots) <= 60:
            raise ValueError("分镜数超限")
    except (ValidationError, ValueError) as exc:
        raise HTTPException(502, "编导返回的分镜结构无效") from exc
    templates = {t.id for t in skill.templates} | {
        t.id for t in get_skill("motion-editorial").templates
    }
    shots = []
    for intent in outline.shots:
        shot = Shot.model_validate(
            intent.model_dump(exclude={"asset_id", "source_state", "source_url"})
        )
        query = shot.visual_query
        # Use exact/tag matches for shots. A related topic alone cannot stand in for a specific requested scene.
        found = [
            a
            for a in project
            if query and query.casefold() in Path(a["filename"]).stem.casefold()
        ]
        if found:
            a = found[0]
            shot.asset_id, shot.source_url = a["id"], a["source_url"]
            shot.source_state = (
                "web_fetched" if a["source_type"] == "web_fetched" else "local_matched"
            )
        elif (
            library
            and query
            and (
                candidates := [
                    a for a in await asset_indexer.search(query) if a.kind != "audio"
                ]
            )
        ):
            try:
                asset = await web_sourcing.attach_library(pid, candidates[0].id)
                shot.asset_id, shot.source_state = asset.id, "local_matched"
            except (HTTPException, OSError):
                pass
        if not shot.asset_id and intent.allow_web and body.web_enabled and query:
            try:
                hits = await web_sourcing.search(query)
                if hits:
                    hit = hits[0]
                    response = await web_sourcing.fetch(
                        pid,
                        hit["url"],
                        media_url=hit.get("media_url"),
                        license=hit.get("license"),
                    )
                    asset = response["asset"]
                    if asset.kind != "audio":
                        shot.asset_id, shot.source_url, shot.source_state = (
                            asset.id,
                            asset.source_url,
                            "web_fetched",
                        )
            except (HTTPException, ValueError, OSError, TimeoutError):
                pass
        if not shot.asset_id and shot.component_id in templates:
            shot.source_state = "motion_generated"
            shot.props = {"title": shot.title, **shot.props}
        if shot.source_state == "placeholder":
            shot.placeholder_hint = f"请补充「{query or shot.title}」的图片或 {shot.duration_ms / 1000:g} 秒录屏"
        shots.append(shot)
    result = {"reply": outline.reply, "shots": shots, "base_revision": doc.revision}
    if body.auto_apply:
        result["timeline"] = await apply_plan(
            pid,
            Plan(
                **body.model_dump(exclude={"base_revision"}),
                base_revision=body.base_revision
                if body.base_revision is not None
                else doc.revision,
                shots=shots,
            ),
        )
    return result


async def voice_asset(pid, project, shot, temp):
    try:
        async with asyncio.timeout(20):
            await router.synthesize(
                temp,
                shot.narration,
                project["voice"],
                project["speech_rate"],
            )
    except (
        TimeoutError,
        RuntimeError,
        ValueError,
        HTTPException,
        OSError,
        OpenAIError,
        ClientError,
    ):
        await asyncio.to_thread(
            tts.mock_voice, temp, shot.narration, project["speech_rate"]
        )
    path = temp / "audio.mp3"
    data = path.read_bytes()
    return await web_sourcing.publish(
        pid,
        path,
        shot.title + ".mp3",
        len(data),
        hashlib.sha256(data).hexdigest(),
        "narration",
    )


def playable_media(pid, asset):
    return bool(
        asset
        and asset["kind"] in {"video", "image"}
        and asset["width"]
        and asset["height"]
        and (asset["kind"] != "video" or asset["duration_ms"])
        and resolve_safe_path(project_dir(pid), asset["rel_path"]).is_file()
    )


async def apply_plan(pid, body):
    doc = await engine.get(pid)
    revision = doc.revision if body.base_revision is None else body.base_revision
    if revision != doc.revision:
        raise RevisionConflict(doc.revision)
    skill = skill_for(body.skill_id)
    allowed = {
        t.id: t.props_schema
        for s in [skill, get_skill("motion-editorial")]
        for t in s.templates
    }
    assets = {a["id"]: a for a in await repo.media_assets(pid)}
    project = await repo.project(pid)
    tracks = {name: [] for name in ("video", "overlay", "subtitle", "audio")}
    pos, created = 0, []
    async with project_files(pid):
        try:
            for i, shot in enumerate(body.shots):
                timing = {"start_ms": pos, "end_ms": pos + shot.duration_ms}
                clip = dict(
                    id=shot.id,
                    source_state=shot.source_state,
                    text=shot.title,
                    **timing,
                )
                asset = assets.get(shot.asset_id)
                if shot.source_state in {
                    "web_fetched",
                    "local_matched",
                } and playable_media(pid, asset):
                    clip.update(
                        kind=asset["kind"] + "_clip",
                        asset_id=asset["id"],
                        source_url=asset["source_url"],
                    )
                    if asset["kind"] == "video" and asset["duration_ms"]:
                        clip["speed"] = min(1, asset["duration_ms"] / shot.duration_ms)
                elif (
                    shot.source_state == "motion_generated"
                    and shot.component_id in allowed
                ):
                    schema = allowed[shot.component_id]
                    props = {
                        k: v
                        for k, v in shot.props.items()
                        if k != "src" and k in schema.get("properties", {})
                    }
                    if not Draft202012Validator(schema).is_valid(props):
                        raise HTTPException(
                            422, f"「{shot.title}」的动效属性与模板不符"
                        )
                    if shot.component_id in {
                        "pip_commentary",
                        "image_card",
                    } and playable_media(pid, asset):
                        props["src"] = f"/api/media/{asset['id']}/stream"
                        props["media_type"] = asset["kind"]
                    clip.update(
                        kind="motion_card",
                        component_id=shot.component_id,
                        props={"title": shot.title, **props},
                    )
                else:
                    clip.update(
                        kind="placeholder",
                        source_state="placeholder",
                        prompt_hint=shot.placeholder_hint
                        or f"待补充：{shot.visual_query or shot.title}",
                    )
                clip["visual_query"] = shot.visual_query
                tracks["video"].append(clip)
                if body.skill_id == "ai-news-montage":
                    template = "lower_third" if i % 2 == 0 else "ticker_banner"
                    tracks["overlay"].append(
                        dict(
                            id="ov_" + shot.id,
                            kind="motion_card",
                            component_id=template,
                            props={"title": shot.title},
                            **timing,
                        )
                    )
                if shot.narration:
                    tracks["subtitle"].append(
                        dict(
                            id="sub_" + shot.id,
                            kind="subtitle",
                            text=shot.narration,
                            **timing,
                        )
                    )
                    with TemporaryDirectory(dir=project_dir(pid)) as tmp:
                        voice = await voice_asset(pid, project, shot, Path(tmp))
                    created.append(voice)
                    tracks["audio"].append(
                        dict(
                            id="voice_" + shot.id,
                            kind="narration",
                            asset_id=voice.id,
                            speed=max(1, (voice.duration_ms or 0) / shot.duration_ms),
                            **timing,
                        )
                    )
                pos += shot.duration_ms
            return await engine.patch(
                pid,
                TimelinePatchRequest(
                    base_revision=revision,
                    author="internal_ai",
                    summary=f"应用导演分镜 · {len(body.shots)} 幕",
                    ops=[
                        {
                            "op": "apply_plan",
                            "tracks": tracks,
                            "skill_id": body.skill_id,
                            "aspect_ratio": body.aspect_ratio,
                        }
                    ],
                ),
            )
        except BaseException:
            for asset in created:
                await repo.execute("DELETE FROM media_assets WHERE id=?", asset.id)
                resolve_safe_path(project_dir(pid), asset.path).unlink(missing_ok=True)
            raise
