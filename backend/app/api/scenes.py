import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, TypeAdapter

from app.agents.base import BaseAgent
from app.api.pipeline import locks, tasks
from app.api.projects import get
from app.core.events import emit
from app.db import repository as repo
from app.media import renderer, tts
from app.media.hash_util import content_hash
from app.pipeline.orchestrator import folder, script_snapshot
from app.schemas.storyboard import SceneItem

router = APIRouter(prefix="/api/projects")
fields = ("template_type", "narration", "visual_payload", "source_ids")


@asynccontextmanager
async def editable(pid):
    async with locks[pid]:
        p = await get(pid)
        if pid in tasks or p["status"] not in ("COMPLETED", "WAITING_STORYBOARD"):
            raise HTTPException(409, "当前状态不支持编辑")
        yield p, await repo.scenes(pid)


def find(rows, sid):
    for row in rows:
        if row["id"] == sid:
            return row
    raise HTTPException(404, "找不到分镜")


def draft(row, changes):
    try:
        data = (
            TypeAdapter(SceneItem)
            .validate_python({**{k: row[k] for k in fields}, **changes})
            .model_dump()
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if (data["template_type"] == "cover") != (row["order_index"] == 1):
        raise HTTPException(422, "封面固定在第一幕")
    return {**row, **data}


async def arrange(pid, ids, **kwargs):
    await repo.arrange(pid, ids, **kwargs)
    await script_snapshot(pid)
    await emit(pid, "EDITOR", "分镜编排已更新")


@router.post("/{pid}/scenes", status_code=201)
async def add(pid: str, scene: SceneItem):
    async with editable(pid) as (_, rows):
        allowed = {s["id"] for s in await repo.sources(pid)}
        if (
            scene.template_type == "cover"
            or not scene.source_ids
            or set(scene.source_ids) - allowed
        ):
            raise HTTPException(422, "新增幕需要有效来源，且不能重复封面")
        sid = uuid4().hex
        await arrange(pid, [s["id"] for s in rows] + [sid], add=(sid, scene))
        return {"id": sid}


class Order(BaseModel):
    scene_ids: list[str]


@router.put("/{pid}/scenes/reorder")
async def reorder(pid: str, body: Order):
    async with editable(pid) as (_, rows):
        ids = body.scene_ids
        if (
            not ids
            or ids[0] != rows[0]["id"]
            or sorted(ids) != sorted(s["id"] for s in rows)
        ):
            raise HTTPException(422, "顺序必须包含全部分镜且保留首幕封面")
        await arrange(pid, ids)
        return {"scene_ids": ids}


@router.delete("/{pid}/scenes/{sid}")
async def delete(pid: str, sid: str):
    async with editable(pid) as (_, rows):
        row = find(rows, sid)
        if row["order_index"] == 1:
            raise HTTPException(422, "封面不可删除")
        await arrange(pid, [s["id"] for s in rows if s["id"] != sid], remove=sid)
        return {"removed": sid}


@router.post("/{pid}/scenes/{sid}/preview")
async def preview(pid: str, sid: str, changes: dict | None = None):
    async with editable(pid) as (p, rows):
        scene = draft(find(rows, sid), changes or {})
        with tempfile.TemporaryDirectory(
            dir=folder(pid), ignore_cleanup_errors=True
        ) as tmp:
            path = Path(tmp)
            await asyncio.to_thread(renderer.render, path, p, scene, len(rows))
            return Response(
                (path / "card.png").read_bytes(),
                media_type="image/png",
                headers={"Cache-Control": "no-store"},
            )


class Speech(BaseModel):
    narration: str = Field(min_length=1, max_length=460)


@router.post("/{pid}/scenes/{sid}/audition")
async def audition(pid: str, sid: str, body: Speech):
    async with editable(pid) as (p, rows):
        find(rows, sid)
        with tempfile.TemporaryDirectory(
            dir=folder(pid), ignore_cleanup_errors=True
        ) as tmp:
            path = Path(tmp)
            await tts.narrate(path, body.narration, p["voice"], p["target_format"])
            return Response((path / "audio.mp3").read_bytes(), media_type="audio/mpeg")


class Rewrite(BaseModel):
    intent: str = Field(min_length=1, max_length=240)
    narration: str | None = Field(default=None, max_length=460)


class SceneWriter(BaseAgent):
    async def process(self, scene, intent, sources):
        def sample():
            original = scene["narration"].strip()
            parts = [part for part in original.split("。") if part]
            if any(t in intent for t in ("短", "精简", "简洁")):
                return {"narration": (parts or [original])[0] + "。"}
            p = scene["visual_payload"]
            idea = next(
                (
                    p[k]
                    for k in ("takeaway", "context", "subtitle", "quote", "heading")
                    if k in p
                ),
                original,
            )
            lead = (
                "你留意过这个细节吗？"
                if any(t in intent for t in ("口语", "活泼", "提问"))
                else "先看这条线索。"
            )
            return {"narration": lead + idea + "。" + (parts or [original])[-1] + "。"}

        result = await self.llm.json(
            "只改写单幕中文旁白，遵循用户意图并保持数字、事实与溯源。返回 narration 字符串。",
            {"scene": scene, "intent": intent, "sources": sources},
            sample,
        )
        return Speech.model_validate(result)


@router.post("/{pid}/scenes/{sid}/rewrite")
async def rewrite(pid: str, sid: str, body: Rewrite):
    async with editable(pid) as (_, rows):
        row = find(rows, sid)
        scene = {k: row[k] for k in fields}
        if body.narration:
            scene["narration"] = body.narration
        sources = [s for s in await repo.sources(pid) if s["id"] in scene["source_ids"]]
        return await SceneWriter().run(pid, scene, body.intent, sources)


@router.get("/{pid}/scenes/{sid}/thumbnail")
async def thumbnail(pid: str, sid: str):
    async with locks[pid]:
        p = await get(pid)
        rows = await repo.scenes(pid)
        row = find(rows, sid)
        root = folder(pid)
        if (
            row["render_status"] == "READY"
            and (root / "scenes" / sid / "card.png").is_file()
        ):
            return Response(
                (root / "scenes" / sid / "card.png").read_bytes(),
                media_type="image/png",
            )
        dest = root / "previews" / sid
        digest = content_hash(p, row, len(rows))
        marker = dest / "hash"
        if (
            not marker.is_file()
            or marker.read_text() != digest
            or not (dest / "card.png").is_file()
        ):
            dest.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(renderer.render, dest, p, row, len(rows))
            marker.write_text(digest)
        return Response((dest / "card.png").read_bytes(), media_type="image/png")
