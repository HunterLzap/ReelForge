"""Serialize edits across REST and headless MCP processes with a SQLite write lock."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from fastapi import HTTPException

from app.core.auth import project_dir, resolve_safe_path
from app.core.events import notify
from app.db import repository as repo
from app.db.database import connection
from app.schemas.timeline import (
    FORMATS,
    AddClip,
    Clip,
    DeleteClip,
    Reorder,
    RippleDelete,
    SetBgm,
    SetExportSpec,
    SetSubtitleStyle,
    SplitClip,
    TimelineDocument,
    TimelinePatchRequest,
    UpdateClip,
)

TEMPLATES = {
    "hero_stat": "stat",
    "stat_chart": "stat",
    "compare_split": "compare",
    "bullet_list": "steps",
    "checklist": "steps",
    "big_quote": "quote",
    "timeline": "timeline_card",
}


class RevisionConflict(Exception):
    def __init__(self, revision):
        self.revision = revision


def merge(base, patch):
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            value = merge(result[key], value)
        result[key] = value
    return result


def section(clip, start, end):
    part = dict(clip, start_ms=start, end_ms=end)
    offset = clip["source_in_ms"]
    speed = clip["speed"]
    part["source_in_ms"] = offset + round((start - clip["start_ms"]) * speed)
    if end != clip["end_ms"] or clip["source_out_ms"] is None:
        part["source_out_ms"] = offset + round((end - clip["start_ms"]) * speed)
    return part


def ripple(items, start, end):
    remaining = []
    for clip in items:
        a, b = clip["start_ms"], clip["end_ms"]
        if a < start:
            remaining.append(clip if b <= start else section(clip, a, start))
        if b > end:
            tail = section(clip, max(a, end), b) if a < end else dict(clip)
            if a < start:
                tail["id"] = uuid4().hex
            tail["start_ms"] -= end - start
            tail["end_ms"] -= end - start
            remaining.append(tail)
    return remaining


def apply(doc, op):
    tracks = doc["tracks"]
    if isinstance(op, SetBgm):
        doc["bgm"] = op.bgm
        return
    if isinstance(op, SetSubtitleStyle):
        doc["subtitle_style"] = op.subtitle_style
        return
    if isinstance(op, SetExportSpec):
        doc["export"] = op.export
        for key in ("aspect_ratio", "fps", "resolution"):
            if key in op.export:
                doc[key] = op.export[key]
        if "aspect_ratio" in op.export and "resolution" not in op.export:
            doc.pop("resolution", None)
        return
    if isinstance(op, RippleDelete):
        names = op.tracks or (list(tracks) if op.track == "all" else [op.track])
        start, end = op.start_ms, op.end_ms
        if op.clip_id:
            target = next(
                (c for name in names for c in tracks[name] if c["id"] == op.clip_id),
                None,
            )
            if target is None:
                raise ValueError("找不到波纹删除的片段")
            start, end = target["start_ms"], target["end_ms"]
        if start is None or end is None or end <= start:
            raise ValueError("波纹删除需要有效的时间范围")
        for name in set(names):
            tracks[name] = ripple(tracks[name], start, end)
        return
    items = tracks[op.track]
    if isinstance(op, AddClip):
        if op.index is not None and op.index > len(items):
            raise ValueError("插入位置超出轨道")
        start = (
            max((c["end_ms"] for c in items[: op.index]), default=0)
            if op.track == "video"
            else 0
        )
        values = {"kind": op.track, "start_ms": start, **op.clip}
        clip = Clip.model_validate(values).model_dump()
        if op.index is None:
            items.append(clip)
            items.sort(key=lambda c: c["start_ms"])
        else:
            items.insert(op.index, clip)
            if op.track == "video" and "start_ms" not in op.clip:
                contiguous(items)
        return

    index = next((i for i, c in enumerate(items) if c["id"] == op.clip_id), None)
    if index is None:
        raise ValueError("指定轨道上没有该片段")
    clip = items[index]
    if isinstance(op, DeleteClip):
        items.pop(index)
    elif isinstance(op, UpdateClip):
        if "id" in op.patch and op.patch["id"] != clip["id"]:
            raise ValueError("不能修改片段 ID")
        values = merge(clip, op.patch)
        if "duration_ms" in op.patch and "end_ms" not in op.patch:
            values.pop("end_ms")
        items[index] = Clip.model_validate(values).model_dump()
    elif isinstance(op, SplitClip):
        if not clip["start_ms"] < op.at_ms < clip["end_ms"]:
            raise ValueError("切分点必须位于片段内部")
        items[index : index + 1] = [
            section(clip, clip["start_ms"], op.at_ms),
            dict(section(clip, op.at_ms, clip["end_ms"]), id=uuid4().hex),
        ]
    elif isinstance(op, Reorder):
        if op.target_index >= len(items):
            raise ValueError("目标位置超出轨道")
        items.insert(op.target_index, items.pop(index))
        if op.track == "video":
            contiguous(items)


def contiguous(items):
    pos = 0
    for clip in items:
        end = pos + clip["end_ms"] - clip["start_ms"]
        clip.update(start_ms=pos, end_ms=end)
        pos = end


async def migrate(project):
    pid = project["id"]
    doc = TimelineDocument.model_validate(
        {
            "project_id": pid,
            "aspect_ratio": project["aspect_ratio"]
            or FORMATS[project["target_format"]],
            "skill_id": project["skill_id"] or "motion-editorial",
            "theme": project["theme"],
            "subtitle_style": project["subtitle_style"],
        }
    ).model_dump()
    pos = 0
    for scene in await repo.scenes(pid):
        sid = scene["id"]
        end = pos + (scene["duration_ms"] or 3000)
        timing = {"start_ms": pos, "end_ms": end}
        props = scene["visual_payload"]
        if props.get("image_asset"):
            props["src"] = f"/workspace/{pid}/assets/{props['image_asset']}"
        template = scene["template_type"]
        doc["tracks"]["video"].append(
            dict(
                timing,
                id=sid,
                kind="motion_card",
                component_id=TEMPLATES.get(template, template),
                props=props,
            )
        )
        if scene["narration"]:
            doc["tracks"]["subtitle"].append(
                dict(timing, id="sub_" + sid, kind="subtitle", text=scene["narration"])
            )
            path = f"scenes/{sid}/audio.mp3"
            if resolve_safe_path(project_dir(pid), path).is_file():
                doc["tracks"]["audio"].append(
                    dict(
                        timing,
                        id="audio_" + sid,
                        kind="narration",
                        src=f"/workspace/{pid}/{path}",
                    )
                )
        pos = end
    return TimelineDocument.model_validate(doc)


def write_snapshot(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        try:
            tmp.write(data.encode())
            tmp.close()
            Path(tmp.name).replace(path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class TimelineEngine:
    async def get(self, pid):
        return await self._transaction(pid)

    async def patch(self, pid, request: TimelinePatchRequest):
        return await self._transaction(pid, "patch", request.base_revision, request)

    async def undo(self, pid, base_revision=None):
        return await self._transaction(pid, "undo", base_revision)

    async def redo(self, pid, base_revision=None):
        return await self._transaction(pid, "redo", base_revision)

    async def _transaction(self, pid, action=None, base=None, request=None):
        async with connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            projects = await db.execute_fetchall(
                "SELECT * FROM projects WHERE id=?", (pid,)
            )
            if not projects:
                raise HTTPException(404, "项目不存在")
            path = resolve_safe_path(project_dir(pid), "timeline.json")
            rows = await db.execute_fetchall(
                "SELECT * FROM timelines WHERE project_id=?", (pid,)
            )
            if not rows:
                if path.is_file():
                    doc = TimelineDocument.model_validate_json(path.read_bytes())
                    if doc.project_id != pid:
                        raise HTTPException(409, "现有时间轴的工程 ID 不一致")
                else:
                    doc = await migrate(projects[0])
                history, cursor = [doc.revision], 0
                await self._save(db, doc, history, cursor, "初始化时间轴", "system")
            else:
                row = rows[0]
                doc = TimelineDocument.model_validate_json(row["timeline_json"])
                history, cursor = json.loads(row["history_json"]), row["cursor"]
            if base is not None and base != doc.revision:
                raise RevisionConflict(doc.revision)
            if action:
                revision = doc.revision + 1
                if action == "patch":
                    values = doc.model_dump()
                    try:
                        for op in request.ops:
                            apply(values, op)
                        doc = TimelineDocument.model_validate(values)
                    except (ValueError, TypeError) as exc:
                        raise HTTPException(422, str(exc)) from exc
                    history = history[: cursor + 1] + [revision]
                    cursor += 1
                    summary, author = request.summary, request.author
                else:
                    cursor += -1 if action == "undo" else 1
                    if not 0 <= cursor < len(history):
                        raise HTTPException(409, "没有可撤销或重做的修订")
                    snapshot = await db.execute_fetchall(
                        "SELECT timeline_json FROM timeline_revisions WHERE project_id=? AND revision=?",
                        (pid, history[cursor]),
                    )
                    doc = TimelineDocument.model_validate_json(snapshot[0][0])
                    summary, author = action, "user"
                doc.revision = revision
                await self._save(db, doc, history, cursor, summary, author)
            if action or not rows:
                await db.execute(
                    "INSERT INTO event_logs(project_id,level,stage_name,message) VALUES(?, 'info', 'timeline_updated', ?)",
                    (pid, repo.dump({"revision": doc.revision})),
                )
            data = doc.model_dump_json()
            # Also repair the materialized file following an interrupted DB commit.
            if action or not path.exists() or path.read_text("utf-8") != data:
                write_snapshot(path, data)
        if action or not rows:
            notify(pid)
        return doc

    async def _save(self, db, doc, history, cursor, summary, author):
        data = doc.model_dump_json()
        await db.execute(
            "INSERT INTO timelines(project_id,revision,timeline_json,history_json,cursor) VALUES(?,?,?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET revision=excluded.revision,timeline_json=excluded.timeline_json,"
            "history_json=excluded.history_json,cursor=excluded.cursor,updated_at=CURRENT_TIMESTAMP",
            (doc.project_id, doc.revision, data, json.dumps(history), cursor),
        )
        await db.execute(
            "INSERT INTO timeline_revisions(project_id,revision,op_summary,timeline_json,author) VALUES(?,?,?,?,?)",
            (doc.project_id, doc.revision, summary, data, author),
        )
        await db.execute(
            "UPDATE projects SET timeline_revision=?,skill_id=?,aspect_ratio=? WHERE id=?",
            (doc.revision, doc.skill_id, doc.aspect_ratio, doc.project_id),
        )


engine = TimelineEngine()
