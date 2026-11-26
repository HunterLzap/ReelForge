from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.external import idle
from app.api.pipeline import locks
from app.core.events import emit
from app.db import repository as repo
from app.media.assembler import export_timeline
from app.media.limits import project_files
from app.schemas.timeline import TimelineDocument, TimelinePatchRequest
from app.services.timeline_engine import RevisionConflict, engine

router = APIRouter(prefix="/api/projects/{pid}")


async def conflict_handler(request, exc: RevisionConflict):
    return JSONResponse(
        {"detail": "时间轴版本冲突，请重新读取", "current_revision": exc.revision}, 409
    )


@router.get("/timeline")
async def timeline(pid: str) -> TimelineDocument:
    return await engine.get(pid)


@router.post("/timeline/patch")
@router.patch("/timeline")
async def patch(pid: str, body: TimelinePatchRequest) -> TimelineDocument:
    return await engine.patch(pid, body)


class HistoryRequest(BaseModel):
    base_revision: int | None = Field(None, ge=0)


@router.post("/timeline/undo")
async def undo(pid: str, body: HistoryRequest | None = None) -> TimelineDocument:
    return await engine.undo(pid, body.base_revision if body else None)


@router.post("/timeline/redo")
async def redo(pid: str, body: HistoryRequest | None = None) -> TimelineDocument:
    return await engine.redo(pid, body.base_revision if body else None)


@router.get("/timeline/revisions")
async def revisions(pid: str):
    await engine.get(pid)
    return await repo.revisions(pid)


@router.post("/export")
@router.post("/timeline/export")
async def export(pid: str):
    async with locks[pid], project_files(pid):
        await idle(pid)
        doc = await engine.get(pid)
        await emit(
            pid, "stage", repo.dump({"stage": "render", "revision": doc.revision})
        )
        try:
            result = await export_timeline(doc)
        except Exception as exc:
            await emit(pid, "error", str(exc), "error")
            if isinstance(exc, ValueError):
                raise HTTPException(422, str(exc)) from exc
            if isinstance(exc, RuntimeError):
                raise HTTPException(500, str(exc)) from exc
            raise
        await emit(pid, "export_done", repo.dump(result))
        return result
