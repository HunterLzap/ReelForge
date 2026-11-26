from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.pipeline import locks
from app.api.projects import get
from app.core.auth import project_dir, resolve_safe_path
from app.core.events import emit
from app.db import repository as repo
from app.schemas.review_pin import PinCreate, PinUpdate, ReviewPin
from app.services import chat_editor, pin_service

router = APIRouter(prefix="/api/projects/{pid}/pins")


@router.get("", response_model=list[ReviewPin])
async def listing(pid: str):
    await get(pid)
    return [
        pin_service.serialize(r)
        for r in await repo.rows(
            "SELECT * FROM review_pins WHERE project_id=? ORDER BY rowid", pid
        )
    ]


@router.post("", status_code=201, response_model=ReviewPin)
async def create(pid: str, body: PinCreate):
    async with locks[pid]:
        return await pin_service.create(pid, body)


@router.patch("/{pin_id}", response_model=ReviewPin)
async def update(pid: str, pin_id: str, body: PinUpdate):
    async with locks[pid]:
        return await pin_service.update(pid, pin_id, body)


class FixRequest(BaseModel):
    base_revision: int | None = Field(None, ge=0)
    author: Literal["internal_ai", "external_mcp"] = "internal_ai"


@router.post("/{pin_id}/ai-fix", response_model=chat_editor.PinFixResult)
async def ai_fix(pid: str, pin_id: str, body: FixRequest | None = None):
    body = body or FixRequest()
    return await chat_editor.fix_pin(pid, pin_id, body.base_revision, body.author)


@router.delete("/{pin_id}")
async def delete(pid: str, pin_id: str):
    async with locks[pid]:
        pin = await pin_service.lookup(pid, pin_id)
        path = resolve_safe_path(project_dir(pid), pin.frame_path)
        await repo.execute(
            "DELETE FROM review_pins WHERE project_id=? AND id=?", pid, pin_id
        )
        path.unlink(missing_ok=True)
        await emit(pid, "pin_updated", repo.dump({"pin_id": pin_id}))
    return {"deleted": pin_id}


@router.get("/{pin_id}/frame")
async def frame(pid: str, pin_id: str):
    pin = await pin_service.lookup(pid, pin_id)
    path = resolve_safe_path(project_dir(pid), pin.frame_path)
    if not path.is_file():
        raise HTTPException(404, "批注截帧不存在")
    return FileResponse(path, media_type="image/png")
