import asyncio
import shutil
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.pipeline import locks, schedule, tasks
from app.api.projects import get
from app.core.config import settings
from app.core.events import emit
from app.db import repository as repo
from app.db.database import connection
from app.media.assembler import duration
from app.media.renderer import SIZES
from app.pipeline.orchestrator import folder, read, script_snapshot, snapshot, state
from app.schemas.project import FormatType, MediaSettings, ProjectCreate
from app.schemas.research import ResearchPack
from app.schemas.storyboard import StoryboardScript

router = APIRouter(prefix="/api/projects")


async def idle(pid):
    await get(pid)
    if pid in tasks and not tasks[pid].done():
        raise HTTPException(409, "项目正在运行")


@router.post("/{pid}/research")
async def research(pid: str, body: ResearchPack):
    async with locks[pid]:
        await idle(pid)
        ids = {source.id for source in body.sources}
        if len(ids) != len(body.sources):
            raise HTTPException(422, "sources.id 不可重复")
        evidence = [x.source_ids for x in body.key_facts + body.data_points]
        rows = await repo.scenes(pid)
        if any(set(refs) - ids for refs in evidence + [s["source_ids"] for s in rows]):
            raise HTTPException(422, "source_ids 包含未列入 sources 的编号")
        await repo.save_sources(pid, body)
        snapshot(pid, "research", body.model_dump(mode="json"))
        snapshot(pid, "fact_check", None)
        await state(
            pid,
            "WAITING_STORYBOARD" if rows else "WAITING_OUTLINE",
            "已收到外部采编资料",
        )
    return {"saved": True}


@router.put("/{pid}/storyboard")
async def storyboard(pid: str, body: StoryboardScript):
    async with locks[pid]:
        await idle(pid)
        ids = {s["id"] for s in await repo.sources(pid)}
        for i, scene in enumerate(body.scenes):
            check_image(pid, scene.visual_payload)
            if not scene.source_ids or set(scene.source_ids) - ids:
                raise HTTPException(
                    422,
                    [
                        {
                            "loc": ["body", "scenes", i, "source_ids"],
                            "msg": "请引用已保存的来源编号",
                        }
                    ],
                )
        await repo.save_script(pid, body)
        await script_snapshot(pid)
        await state(pid, "WAITING_STORYBOARD", "已收到外部分镜")
    return {"saved": len(body.scenes)}


def artifact(p):
    cards = p["target_format"] == "cards_3_4"
    path = folder(p["id"]) / "output" / ("cards.zip" if cards else "final.mp4")
    return {
        "path": str(path),
        "preview_url": f"/workspace/{p['id']}/output/{path.name}",
        "resolution": SIZES[p["target_format"]],
        "duration_ms": 0 if cards else duration(path),
    }


class RenderRequest(BaseModel):
    wait: bool = True
    rebuild_only: bool = False


@router.post("/{pid}/render")
async def render(pid: str, body: RenderRequest | None = None):
    body = body or RenderRequest()
    task = await schedule(pid, "rebuild" if body.rebuild_only else "render")
    if not body.wait:
        return {"accepted": True}
    try:
        cache = await asyncio.shield(task)
    except asyncio.CancelledError:
        if task.cancelled():
            raise HTTPException(409, "渲染已中止") from None
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return {**await asyncio.to_thread(artifact, await get(pid)), "cache": cache}


@router.get("/{pid}/status")
async def project_status(pid: str):
    p = await get(pid)
    scenes = await repo.scenes(pid)
    return {
        "project_id": pid,
        "status": p["status"],
        "error": p["error_message"],
        "scenes": [
            {
                **row,
                "thumbnail_url": f"/api/projects/{pid}/scenes/{row['id']}/thumbnail",
            }
            for row in scenes
        ],
        "artifact": await asyncio.to_thread(artifact, p)
        if p["status"] == "COMPLETED"
        else None,
    }


def check_image(pid, payload):
    from app.media.assets import validate_image

    try:
        validate_image(pid, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/{pid}/settings")
async def media_settings(pid: str, body: MediaSettings):
    async with locks[pid]:
        await idle(pid)
        p = await get(pid)
        values = {**p, **body.model_dump(exclude_unset=True)}
        if any(values[k] != p[k] for k in MediaSettings.model_fields):
            async with connection() as c:
                await c.execute(
                    "UPDATE projects SET transition=?,subtitle_style=?,speech_rate=? WHERE id=?",
                    (
                        values["transition"],
                        values["subtitle_style"],
                        values["speech_rate"],
                        pid,
                    ),
                )
                await c.execute(
                    "UPDATE scenes SET render_status='DIRTY' WHERE project_id=?", (pid,)
                )
            await emit(pid, "EDITOR", "成片参数已保存")
        return await get(pid)


class CloneRequest(BaseModel):
    target_format: FormatType | None = None
    theme: Literal["editorial_dark", "clean_light", "warm_amber"] | None = None
    topic: str | None = Field(default=None, min_length=1, max_length=240, pattern=r"\S")


@router.post("/{pid}/clone", status_code=201)
async def clone(pid: str, body: CloneRequest):
    async with locks[pid]:
        await idle(pid)
        original = await get(pid)
        scenes = read(pid, "storyboard")
        if not scenes:
            raise HTTPException(409, "项目尚无分镜可克隆")
        data = ProjectCreate(
            **{k: original[k] for k in ProjectCreate.model_fields}
            | body.model_dump(exclude_none=True)
        )
        created = await repo.create(data)
        dest = created["id"]
        try:
            pack = read(pid, "research")
            if pack:
                await repo.save_sources(dest, ResearchPack.model_validate(pack))
                snapshot(dest, "research", pack)
            report = read(pid, "fact_check")
            if report:
                snapshot(dest, "fact_check", report)
            if (folder(pid) / "assets").exists():
                await asyncio.to_thread(
                    shutil.copytree, folder(pid) / "assets", folder(dest) / "assets"
                )
            await repo.save_script(dest, StoryboardScript.model_validate(scenes))
            await script_snapshot(dest)
            await state(dest, "WAITING_STORYBOARD", "已克隆分镜，等待渲染")
        except BaseException:
            await repo.delete_project(dest)
            shutil.rmtree(folder(dest), ignore_errors=True)
            raise
        return await get(dest)


@router.delete("/{pid}")
async def delete_project(pid: str):
    async with locks[pid]:
        await idle(pid)
        root = folder(pid)
        if root.is_symlink() or root.resolve().parent != settings().workspace_dir:
            raise HTTPException(409, "项目路径无效")
        trash = root.with_name(".deleting-" + pid)
        if root.exists():
            root.rename(trash)
        try:
            await repo.delete_project(pid)
        except BaseException:
            if trash.exists():
                trash.rename(root)
            raise
        if trash.exists():
            await asyncio.to_thread(shutil.rmtree, trash)
        return {"deleted": pid}
