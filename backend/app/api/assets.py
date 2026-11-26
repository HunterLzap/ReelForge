import asyncio

from fastapi import APIRouter, HTTPException, UploadFile

from app.api.external import idle
from app.api.pipeline import locks
from app.api.projects import get
from app.media import assets
from app.pipeline.orchestrator import folder

router = APIRouter(prefix="/api/projects")


@router.post("/{pid}/assets", status_code=201)
async def upload(pid: str, file: UploadFile):
    async with locks[pid]:
        await idle(pid)
        data = await file.read(assets.LIMIT + 1)
        if len(data) > assets.LIMIT:
            raise HTTPException(413, "图片超过 10 MB")
        try:
            return await asyncio.to_thread(assets.store, pid, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


@router.get("/{pid}/assets")
async def listing(pid: str):
    await get(pid)
    return [
        {"asset_id": p.name, "url": f"/workspace/{pid}/assets/{p.name}"}
        for p in sorted((folder(pid) / "assets").glob("*"))
        if p.is_file() and not p.is_symlink() and p.suffix in {".jpg", ".png", ".webp"}
    ]
