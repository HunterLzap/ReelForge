import asyncio
import base64
import json
import tempfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image

from app.core.auth import project_dir, resolve_safe_path
from app.core.events import emit, notify, record
from app.db import repository as repo
from app.db.database import connection
from app.media.remotion_runner import render_timeline
from app.schemas.review_pin import ReviewPin
from app.schemas.timeline import TimelineDocument
from app.services.timeline_engine import engine


def serialize(row):
    pid, pin_id = row["project_id"], row["id"]
    return ReviewPin(
        **row,
        bbox=json.loads(row["bbox_json"]),
        frame_path=row["frame_rel_path"],
        frame_url=f"/api/projects/{pid}/pins/{pin_id}/frame",
    )


async def lookup(pid, pin_id):
    rows = await repo.rows(
        "SELECT * FROM review_pins WHERE project_id=? AND id=?", pid, pin_id
    )
    if not rows:
        raise HTTPException(404, "批注不存在")
    return serialize(rows[0])


def supplied_frame(url, dest):
    prefix = "data:image/png;base64,"
    if not url.startswith(prefix):
        raise HTTPException(422, "截帧必须为 PNG data URL")
    try:
        data = base64.b64decode(url[len(prefix) :], validate=True)
        with Image.open(BytesIO(data), formats=["PNG"]) as img:
            if img.width * img.height > 16_777_216:
                raise ValueError("截帧过大")
            img.verify()
        dest.write_bytes(data)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "无效的 PNG 截帧") from exc


async def create(pid, body):
    doc = await engine.get(pid)
    if body.revision is not None and body.revision != doc.revision:
        rows = await repo.rows(
            "SELECT timeline_json FROM timeline_revisions WHERE project_id=? AND revision=?",
            pid,
            body.revision,
        )
        if not rows:
            raise HTTPException(422, "时间轴修订不存在")
        doc = TimelineDocument.model_validate_json(rows[0]["timeline_json"])
    pin_id = uuid4().hex
    rel = f"pins/{pin_id}.png"
    dest = resolve_safe_path(project_dir(pid), rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        frame = Path(tmp) / "frame.png"
        if body.frame_data_url is not None:
            await asyncio.to_thread(supplied_frame, body.frame_data_url, frame)
        elif any(doc.tracks.model_dump().values()):
            last = max(
                c.end_ms
                for name in type(doc.tracks).model_fields
                for c in getattr(doc.tracks, name)
            )
            await render_timeline(
                doc,
                frame,
                frame=min(
                    max(0, round(last * doc.fps / 1000) - 1),
                    round(body.time_ms * doc.fps / 1000),
                ),
            )
        else:
            Image.new(
                "RGB", (doc.resolution.width, doc.resolution.height), "#111a20"
            ).save(frame)
        frame.replace(dest)
        try:
            await repo.execute(
                "INSERT INTO review_pins(id,project_id,revision,time_ms,bbox_json,track,clip_id,note,frame_rel_path,author) VALUES(?,?,?,?,?,?,?,?,?,?)",
                pin_id,
                pid,
                doc.revision,
                body.time_ms,
                repo.dump(body.bbox.model_dump() if body.bbox else None),
                body.track,
                body.clip_id,
                body.note,
                rel,
                body.author,
            )
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
    await emit(pid, "pin_created", pin_id)
    return await lookup(pid, pin_id)


async def update(pid, pin_id, body):
    values = body.model_dump(exclude_unset=True, exclude={"author"})
    if any(values.get(key) is None for key in ("note", "status") if key in values):
        raise HTTPException(422, "状态与批注文字不能为空")
    async with connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        rows = await db.execute_fetchall(
            "SELECT * FROM review_pins WHERE project_id=? AND id=?", (pid, pin_id)
        )
        if not rows:
            raise HTTPException(404, "批注不存在")
        if values.get("status") in {"open", "dismissed"}:
            values["resolved_by_revision"] = None
            values["resolution_summary"] = None
        elif (
            values.get("resolved_by_revision") is not None
            or values.get("status") == "resolved"
        ):
            timeline = (
                await db.execute_fetchall(
                    "SELECT * FROM timelines WHERE project_id=?", (pid,)
                )
            )[0]
            revision = values.get("resolved_by_revision")
            history = json.loads(timeline["history_json"])
            cursor = timeline["cursor"]
            if revision is None or revision == timeline["revision"]:
                revision = history[cursor]
            if revision not in history[: cursor + 1]:
                raise HTTPException(409, "该修订不在当前时间轴历史中")
            values["resolved_by_revision"] = revision
        if values:
            assignments = ", ".join(f"{key}=?" for key in values)
            updated = await db.execute_fetchall(
                f"UPDATE review_pins SET {assignments} WHERE project_id=? AND id=? RETURNING *",
                (*values.values(), pid, pin_id),
            )
            event = (
                "pin_resolved" if values.get("status") == "resolved" else "pin_updated"
            )
            await record(db, pid, event, pin_id=pin_id, author=body.author)
            rows = updated
    if values:
        notify(pid)
    return serialize(dict(rows[0]))
