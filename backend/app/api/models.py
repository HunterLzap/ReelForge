from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.schemas.model_config import DownloadRequest, ModelConfig, Slot, TestSlot
from app.services import model_downloads
from app.services import model_manager as manager

router = APIRouter(prefix="/api/models")


@router.get("")
async def models():
    return dict(
        slots=await manager.slots(),
        catalog=[
            {
                "id": key,
                "slot": item["slot"],
                "provider": item["provider"],
                "size_mb": item["size_mb"],
                "mirrors": item["mirrors"],
            }
            for key, item in manager.CATALOG.items()
        ],
        presets=[
            {"id": k, "name": name, "base_url": url, "api_key_env": env, "model": model}
            for k, (name, url, env, model) in manager.PRESETS.items()
        ],
        **manager.policy(),
    )


@router.put("/{slot}")
async def update(slot: Slot, body: ModelConfig):
    return await manager.save(slot, body)


@router.post("/test")
async def test(body: TestSlot):
    return await manager.connectivity(body.slot)


@router.post("/download")
async def download(body: DownloadRequest):
    return await model_downloads.start(body)


@router.get("/downloads")
async def downloads(request: Request):
    if "text/event-stream" in request.headers.get("accept", ""):
        return StreamingResponse(
            model_downloads.events(request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return model_downloads.listing()


@router.post("/downloads/{task_id}/cancel")
async def cancel(task_id: str):
    return await model_downloads.cancel(task_id)
