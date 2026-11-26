import asyncio

from fastapi import APIRouter, HTTPException, UploadFile

from app.api.external import idle
from app.api.pipeline import locks
from app.api.projects import get
from app.core.auth import project_dir, resolve_safe_path
from app.db import repository as repo
from app.media import assets
from app.media.limits import project_files
from app.pipeline.orchestrator import folder
from app.services.uploads import staged_upload

router = APIRouter(prefix="/api/projects")


@router.post("/{pid}/assets", status_code=201)
async def upload(pid: str, file: UploadFile):
    async with locks[pid], project_files(pid):
        await idle(pid)
        if file.filename and not file.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp")
        ):
            raise HTTPException(422, "请选择 PNG、JPEG 或 WebP 图片")
        directory = resolve_safe_path(project_dir(pid), "assets")
        async with staged_upload(file, directory, assets.LIMIT) as (path, _, digest):
            try:
                return await asyncio.to_thread(assets.store_file, pid, path, digest)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc


@router.post("/{pid}/scenes/{sid}/assets", status_code=201)
async def upload_scene(pid: str, sid: str, file: UploadFile):
    if not any(s["id"] == sid for s in await repo.scenes(pid)):
        raise HTTPException(404, "找不到分镜")
    return await upload(pid, file)


@router.get("/{pid}/assets")
async def listing(pid: str):
    await get(pid)
    return [
        {"asset_id": p.name, "url": f"/workspace/{pid}/assets/{p.name}"}
        for p in sorted((folder(pid) / "assets").glob("*"))
        if p.is_file() and not p.is_symlink() and p.suffix in {".jpg", ".png", ".webp"}
    ]
