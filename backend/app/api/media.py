import asyncio
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.pipeline import locks
from app.api.projects import get
from app.core.auth import project_dir, resolve_safe_path
from app.core.config import settings
from app.db import repository as repo
from app.media import proxy
from app.media.limits import project_files
from app.schemas.asset import EXTENSIONS, MediaAsset
from app.services.uploads import register_media, staged_upload

router = APIRouter(prefix="/api")


@router.post("/media/upload", response_model=MediaAsset, status_code=201)
async def upload(
    file: UploadFile, project_id: str = Form(), generate_proxy: bool = Form(True)
):
    async with locks[project_id], project_files(project_id):
        await get(project_id)
        root = project_dir(project_id)
        name = Path(file.filename or "").name
        ext = Path(name).suffix.lower().lstrip(".")
        kind = next(
            (key for key, allowed in EXTENSIONS.items() if ext in allowed), None
        )
        if not kind:
            raise HTTPException(422, "不支持的媒体扩展名")
        aid = uuid4().hex
        relative = f"media/{aid}.{ext}"
        dest = resolve_safe_path(root, relative)
        proxy_rel = None
        proxy_dest = resolve_safe_path(root, f"proxies/{aid}.mp4")
        async with staged_upload(file, dest.parent) as (tmp, size, digest):
            try:
                metadata = await asyncio.to_thread(proxy.probe, tmp)
            except (RuntimeError, ValueError):
                metadata = {
                    "duration_ms": None,
                    "width": None,
                    "height": None,
                    "fps": None,
                }
            try:
                if (
                    kind == "video"
                    and metadata["width"]
                    and generate_proxy
                    and settings().proxy_profile != "none"
                ):
                    await proxy.generate(tmp, proxy_dest)
                    proxy_rel = str(proxy_dest.relative_to(root))
                tmp.replace(dest)
                return await register_media(
                    project_id,
                    aid,
                    kind,
                    name,
                    relative,
                    metadata,
                    digest,
                    size,
                    "upload",
                    proxy_rel=proxy_rel,
                )
            except BaseException:
                dest.unlink(missing_ok=True)
                proxy_dest.unlink(missing_ok=True)
                raise


@router.get("/projects/{pid}/media", response_model=list[MediaAsset])
async def listing(pid: str):
    await get(pid)
    return await repo.media_assets(pid)


@router.get("/media/{aid}/stream")
async def stream(aid: str, variant: Literal["proxy", "original"] = "original"):
    rows = await repo.rows("SELECT * FROM media_assets WHERE id=?", aid)
    if not rows:
        raise HTTPException(404, "素材不存在")
    asset = rows[0]
    root = project_dir(asset["project_id"])
    if variant == "proxy" and asset["proxy_rel_path"]:
        path = resolve_safe_path(root, asset["proxy_rel_path"])
        if path.is_file():
            return FileResponse(path, media_type="video/mp4")
    path = resolve_safe_path(root, asset["rel_path"])
    if not path.is_file():
        raise HTTPException(404, "原始素材不存在")
    # Starlette FileResponse streams bounded chunks and honors byte ranges / If-Range.
    return FileResponse(path, media_type=asset["mime_type"])
