from typing import Literal

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.schemas.review_pin import BBox
from app.schemas.transcript import RoughCutRequest
from app.services import asr_service
from app.services import screen_editor as editor
from app.services.timeline_engine import engine

router = APIRouter(prefix="/api/projects/{pid}")


class Revision(BaseModel):
    base_revision: int | None = Field(None, ge=0)


class Transcribe(Revision):
    asset_id: str | None = None
    sync_subtitles: bool = True
    hotwords: list[str] | None = None


class Replace(Revision):
    find: str = Field(min_length=1)
    replace: str


class Annotation(Revision):
    kind: Literal["zoom_focus", "spotlight", "callout_box"] = "zoom_focus"
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(2000, gt=0)
    target_bbox: BBox = BBox(x=0.25, y=0.3, w=0.4, h=0.2)
    scale: float = Field(1.65, ge=1, le=4)
    callout_text: str = Field("", max_length=240)


@router.post("/transcribe")
async def transcribe(pid: str, body: Transcribe | None = None):
    body = body or Transcribe()
    timeline, previous = await editor.context(pid, body.base_revision, required=False)
    hotwords = (
        body.hotwords
        if body.hotwords is not None
        else previous.hotwords
        if previous
        else ["ReelForge", "FastAPI"]
    )
    doc = await asr_service.transcribe(timeline, body.asset_id, hotwords)
    ops = (
        editor.subtitle_ops(timeline, doc, clear_all=True)
        if body.sync_subtitles
        else []
    )
    await editor.publish(timeline, ops, "语音识别生成文稿", doc)
    return doc


@router.get("/transcript")
async def transcript(pid: str):
    timeline, doc = await editor.context(pid)
    return {
        "transcript": doc,
        "issues": editor.analyze(timeline, doc),
        "base_revision": timeline.revision,
    }


@router.post("/rough-cut")
async def rough_cut(pid: str, body: RoughCutRequest):
    return await editor.rough_cut(pid, body)


@router.post("/transcript/sync-subtitles")
async def sync(pid: str, body: Revision | None = None):
    body = body or Revision()
    timeline, doc = await editor.context(pid, body.base_revision)
    return await editor.publish(
        timeline, editor.subtitle_ops(timeline, doc, clear_all=True), "从文稿同步字幕"
    )


@router.post("/subtitles/batch-replace")
async def replace(pid: str, body: Replace):
    return await editor.replace(pid, body)


@router.get("/subtitles/export")
async def export(pid: str, format: Literal["srt", "ass"] = "srt"):
    timeline = await engine.get(pid)
    return PlainTextResponse(
        editor.export_subtitles(timeline, format),
        headers={"Content-Disposition": f'attachment; filename="subtitles.{format}"'},
    )


@router.post("/annotations/zoom")
async def annotate(pid: str, body: Annotation):
    timeline, _ = await editor.context(pid, body.base_revision, required=False)
    clip = body.model_dump(exclude={"base_revision"})
    return await editor.publish(
        timeline,
        [{"op": "add_clip", "track": "annotation", "clip": clip}],
        "添加录屏标注",
    )
