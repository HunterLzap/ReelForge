from contextlib import asynccontextmanager

import aiosqlite

from app.core.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, topic TEXT NOT NULL, target_format TEXT NOT NULL, theme TEXT NOT NULL,
 voice TEXT NOT NULL, auto_approve INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
 fact_check_loops INTEGER NOT NULL DEFAULT 0, total_tokens INTEGER NOT NULL DEFAULT 0,
 estimated_cost_cny REAL NOT NULL DEFAULT 0, error_message TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS stage_runs (
 id INTEGER PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), stage_name TEXT NOT NULL,
 attempt INTEGER NOT NULL, status TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
 duration_ms INTEGER NOT NULL, summary TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sources (
 id TEXT, project_id TEXT REFERENCES projects(id), title TEXT, url TEXT, snippet TEXT, credibility_note TEXT,
 PRIMARY KEY(project_id,id));
CREATE TABLE IF NOT EXISTS scenes (
 id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), order_index INTEGER NOT NULL,
 template_type TEXT, narration TEXT, visual_payload_json TEXT, source_ids_json TEXT, content_hash TEXT,
 duration_ms INTEGER DEFAULT 0, render_status TEXT DEFAULT 'DIRTY', UNIQUE(project_id,order_index));
CREATE TABLE IF NOT EXISTS event_logs (
 id INTEGER PRIMARY KEY, project_id TEXT REFERENCES projects(id), level TEXT, stage_name TEXT,
 message TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS timelines (
 project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE, revision INTEGER NOT NULL,
 timeline_json TEXT NOT NULL, history_json TEXT NOT NULL, cursor INTEGER NOT NULL,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS timeline_revisions (
 id INTEGER PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, op_summary TEXT NOT NULL, timeline_json TEXT NOT NULL, author TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(project_id,revision));
CREATE TABLE IF NOT EXISTS media_assets (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, filename TEXT NOT NULL, rel_path TEXT NOT NULL, proxy_rel_path TEXT,
 sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, duration_ms INTEGER, width INTEGER, height INTEGER,
 fps REAL, mime_type TEXT NOT NULL, source_type TEXT NOT NULL, source_url TEXT, license TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS media_project ON media_assets(project_id);
CREATE TABLE IF NOT EXISTS transcripts (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 asset_id TEXT REFERENCES media_assets(id) ON DELETE CASCADE, language TEXT, model_used TEXT,
 segments_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS review_pins (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, time_ms INTEGER NOT NULL, bbox_json TEXT, track TEXT, clip_id TEXT,
 note TEXT NOT NULL, frame_rel_path TEXT, status TEXT NOT NULL DEFAULT 'open', resolved_by_revision INTEGER,
 author TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS pins_project ON review_pins(project_id);
CREATE TABLE IF NOT EXISTS model_configs (
 slot TEXT PRIMARY KEY, provider TEXT, model TEXT, base_url TEXT, api_key_env TEXT, enabled INTEGER,
 extra_json TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS asset_library (
 id TEXT PRIMARY KEY, root_path TEXT NOT NULL, rel_path TEXT NOT NULL, sha256 TEXT, kind TEXT,
 duration_ms INTEGER, width INTEGER, height INTEGER, caption TEXT, tags_json TEXT, quality_flags_json TEXT,
 keyframes_json TEXT, indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(root_path,rel_path));
"""


@asynccontextmanager
async def connection():
    async with aiosqlite.connect(settings().database_path, timeout=20) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        await conn.commit()


async def init():
    cfg = settings()
    cfg.workspace_dir.mkdir(parents=True, exist_ok=True)
    cfg.database_path.parent.mkdir(parents=True, exist_ok=True)
    async with connection() as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(SCHEMA)
        await conn.execute("BEGIN IMMEDIATE")
        columns = await conn.execute_fetchall("PRAGMA table_info(projects)")
        if "seed_only" not in {col["name"] for col in columns}:
            await conn.execute(
                "ALTER TABLE projects ADD COLUMN seed_only INTEGER NOT NULL DEFAULT 0"
            )
        for name, default in (
            ("seed_materials", ""),
            ("brand_label", ""),
            ("transition", "fade"),
            ("subtitle_style", "pill_dark"),
            ("speech_rate", "+0%"),
            ("execution_mode", "api"),
        ):
            columns = await conn.execute_fetchall("PRAGMA table_info(projects)")
            if name not in {col["name"] for col in columns}:
                await conn.execute(
                    f"ALTER TABLE projects ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'"
                )

        existing = {col["name"] for col in columns}
        for name, datatype in (
            ("skill_id", "TEXT"),
            ("timeline_revision", "INTEGER"),
            ("aspect_ratio", "TEXT"),
        ):
            if name not in existing:
                await conn.execute(f"ALTER TABLE projects ADD COLUMN {name} {datatype}")
