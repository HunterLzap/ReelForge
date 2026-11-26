from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.library import IndexRequest, LibraryItem
from app.schemas.timeline import Aspect
from app.services import asset_indexer

router = APIRouter(prefix="/api/library")


@router.post("/index")
async def index(body: IndexRequest | None = None):
    return await asset_indexer.index(body or IndexRequest())


@router.get("/items", response_model=list[LibraryItem])
@router.get("/search", response_model=list[LibraryItem])
async def items(q: str = "", aspect: Aspect | None = None):
    return await asset_indexer.search(q, aspect)


@router.get("/items/{item_id}/thumb")
async def thumbnail(item_id: str):
    entry = await asset_indexer.get(item_id)
    if not entry.keyframes:
        raise HTTPException(404, "该素材没有预览图")
    path = asset_indexer.cache_path(entry.id, entry.keyframes[0])
    if not path.is_file():
        raise HTTPException(404, "缩略图不存在，请重新扫描")
    return FileResponse(path, media_type="image/jpeg")
