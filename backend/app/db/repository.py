import json
from uuid import uuid4

from app.core.config import settings
from app.db.database import connection


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


async def rows(sql, *params):
    async with connection() as c:
        return [dict(row) for row in await c.execute_fetchall(sql, params)]


async def execute(sql, *params):
    async with connection() as c:
        cursor = await c.execute(sql, params)
        return cursor.lastrowid


async def create(data):
    from app.services.model_manager import slots

    voice = data.voice or (await slots())["tts_voice"].model
    pid = uuid4().hex
    await execute(
        "INSERT INTO projects(id,topic,target_format,theme,voice,auto_approve,brand_label,transition,execution_mode,seed_materials,seed_only,subtitle_style,speech_rate,skill_id,aspect_ratio) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        pid,
        data.topic,
        data.target_format,
        data.theme,
        voice,
        data.auto_approve,
        data.brand_label,
        data.transition,
        data.execution_mode,
        data.seed_materials,
        data.seed_only,
        data.subtitle_style,
        data.speech_rate,
        data.skill_id,
        data.aspect_ratio,
    )
    return await project(pid)


async def project(pid):
    result = await rows("SELECT * FROM projects WHERE id=?", pid)
    if not result:
        raise KeyError(pid)
    return result[0]


async def projects(q="", target_format=None, status=None):
    return await rows(
        "SELECT * FROM projects WHERE instr(lower(topic), lower(?)) > 0 AND (? IS NULL OR target_format=?) AND (? IS NULL OR status=?) ORDER BY rowid DESC",
        q,
        target_format,
        target_format,
        status,
        status,
    )


async def delete_project(pid):
    async with connection() as c:
        await c.execute("BEGIN IMMEDIATE")
        for table in ("stage_runs", "sources", "event_logs", "scenes"):
            await c.execute(f"DELETE FROM {table} WHERE project_id=?", (pid,))
        await c.execute("DELETE FROM projects WHERE id=?", (pid,))


async def status(pid, state, error=None):
    await execute(
        "UPDATE projects SET status=?,error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        state,
        error,
        pid,
    )


async def increment_loops(pid):
    await execute(
        "UPDATE projects SET fact_check_loops=fact_check_loops+1 WHERE id=?", pid
    )


async def sources(pid):
    return await rows("SELECT * FROM sources WHERE project_id=? ORDER BY rowid", pid)


async def save_sources(pid, pack):
    async with connection() as c:
        await c.execute("DELETE FROM sources WHERE project_id=?", (pid,))
        await c.executemany(
            "INSERT INTO sources VALUES(?,?,?,?,?,?)",
            [
                (
                    s.id,
                    pid,
                    s.title,
                    str(s.url) if s.url else None,
                    s.snippet,
                    s.credibility_note,
                )
                for s in pack.sources
            ],
        )


async def scenes(pid):
    result = await rows(
        "SELECT * FROM scenes WHERE project_id=? ORDER BY order_index", pid
    )
    for row in result:
        for key in ("visual_payload", "source_ids"):
            row[key] = json.loads(row.pop(key + "_json"))
    return result


def values(s):
    return (
        s.template_type,
        s.narration,
        dump(s.visual_payload.model_dump()),
        dump(s.source_ids),
    )


async def save_script(pid, script):
    async with connection() as c:
        await c.execute("DELETE FROM scenes WHERE project_id=?", (pid,))
        await c.executemany(
            "INSERT INTO scenes(id,project_id,order_index,template_type,narration,visual_payload_json,source_ids_json) VALUES(?,?,?,?,?,?,?)",
            [(uuid4().hex, pid, i, *values(s)) for i, s in enumerate(script.scenes, 1)],
        )


async def edit_scene(pid, sid, scene):
    await execute(
        "UPDATE scenes SET template_type=?,narration=?,visual_payload_json=?,source_ids_json=?,render_status='DIRTY' WHERE project_id=? AND id=?",
        *values(scene),
        pid,
        sid,
    )


async def invalidate(pid, sid):
    await execute(
        "UPDATE scenes SET content_hash=NULL,render_status='DIRTY' WHERE project_id=? AND id=?",
        pid,
        sid,
    )


async def rendered(pid, sid, digest, duration):
    await execute(
        "UPDATE scenes SET content_hash=?,duration_ms=?,render_status='READY' WHERE project_id=? AND id=?",
        digest,
        duration,
        pid,
        sid,
    )


async def stage(pid, name, success, usage, duration, summary):
    async with connection() as c:
        await c.execute(
            "INSERT INTO stage_runs(project_id,stage_name,attempt,status,input_tokens,output_tokens,duration_ms,summary) SELECT ?,?,COUNT(*)+1,?,?,?,?,? FROM stage_runs WHERE project_id=? AND stage_name=?",
            (
                pid,
                name,
                "OK" if success else "FAILED",
                *usage,
                duration,
                summary,
                pid,
                name,
            ),
        )
        cfg = settings()
        cost = (
            usage[0] * cfg.input_cny_per_million + usage[1] * cfg.output_cny_per_million
        ) / 1e6
        await c.execute(
            "UPDATE projects SET total_tokens=total_tokens+?,estimated_cost_cny=estimated_cost_cny+? WHERE id=?",
            (sum(usage), cost, pid),
        )


async def log(pid, name, message, level="info"):
    return await execute(
        "INSERT INTO event_logs(project_id,level,stage_name,message) VALUES(?,?,?,?)",
        pid,
        level,
        name,
        message,
    )


async def logs(pid, after=0):
    return await rows(
        "SELECT * FROM event_logs WHERE project_id=? AND id>? ORDER BY id", pid, after
    )


async def runs(pid):
    return await rows("SELECT * FROM stage_runs WHERE project_id=? ORDER BY id", pid)


async def arrange(pid, ids, *, add=None, remove=None):
    async with connection() as c:
        await c.execute("BEGIN IMMEDIATE")
        if remove:
            await c.execute(
                "DELETE FROM scenes WHERE project_id=? AND id=?", (pid, remove)
            )
        if add:
            sid, scene = add
            await c.execute(
                "INSERT INTO scenes(id,project_id,order_index,template_type,narration,visual_payload_json,source_ids_json) VALUES(?,?,0,?,?,?,?)",
                (sid, pid, *values(scene)),
            )
        await c.execute(
            "UPDATE scenes SET order_index=-order_index WHERE project_id=?", (pid,)
        )
        for index, sid in enumerate(ids, 1):
            await c.execute(
                "UPDATE scenes SET render_status=CASE WHEN order_index!=? OR ? THEN 'DIRTY' ELSE render_status END, order_index=? WHERE project_id=? AND id=?",
                (-index, bool(add or remove), index, pid, sid),
            )


async def media_assets(pid):
    return await rows(
        "SELECT * FROM media_assets WHERE project_id=? ORDER BY rowid", pid
    )


async def revisions(pid):
    return await rows(
        "SELECT revision,op_summary,author,created_at FROM timeline_revisions "
        "WHERE project_id=? ORDER BY revision DESC",
        pid,
    )


async def save_transcript(db, pid, transcript):
    """Insert an immutable snapshot in the same transaction as its timeline pointer."""
    tid = uuid4().hex
    await db.execute(
        "INSERT INTO transcripts(id,project_id,asset_id,language,model_used,segments_json) VALUES(?,?,?,?,?,?)",
        (
            tid,
            pid,
            transcript.asset_id,
            transcript.language,
            transcript.engine,
            transcript.model_dump_json(),
        ),
    )
    return tid


async def get_latest_transcript(pid, timeline=None):
    from app.schemas.transcript import TranscriptDocument

    if timeline is None:
        from app.services.timeline_engine import engine

        timeline = await engine.get(pid)
    result = await rows(
        "SELECT segments_json FROM transcripts WHERE project_id=? AND id=?",
        pid,
        timeline.meta.get("transcript_id"),
    )
    return (
        TranscriptDocument.model_validate_json(result[0]["segments_json"])
        if result
        else None
    )


async def save_media(db, record):
    await db.execute(
        """INSERT INTO media_assets(id,project_id,kind,filename,rel_path,proxy_rel_path,sha256,size_bytes,
        mime_type,source_type,duration_ms,width,height,fps,source_url,license) VALUES(
        :id,:project_id,:kind,:filename,:rel_path,:proxy_rel_path,:sha256,:size_bytes,:mime_type,
        :source_type,:duration_ms,:width,:height,:fps,:source_url,:license)""",
        record,
    )
