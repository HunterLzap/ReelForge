import asyncio
import json

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.api.projects import get
from app.core.events import subscribe
from app.db import repository as repo

router = APIRouter(prefix="/api/projects")


async def stream(pid, request, cursor):
    with subscribe(pid) as signal:
        while not await request.is_disconnected():
            signal.clear()
            for event in await repo.logs(pid, cursor):
                cursor = event["id"]
                name = event["stage_name"]
                named = (
                    f"event: {name}\n"
                    if name
                    in {
                        "timeline_updated",
                        "pin_created",
                        "pin_resolved",
                        "stage",
                        "export_done",
                        "error",
                    }
                    else ""
                )
                yield f"id: {cursor}\n{named}data: {json.dumps(event, ensure_ascii=False)}\n\n"
            try:
                await asyncio.wait_for(signal.wait(), 15)
            except TimeoutError:
                yield ": heartbeat\n\n"


@router.get("/{pid}/stream")
async def events(
    pid: str,
    request: Request,
    after: int = Query(0, ge=0),
    last_event_id: int = Header(0),
):
    await get(pid)
    return StreamingResponse(
        stream(pid, request, max(after, last_event_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
