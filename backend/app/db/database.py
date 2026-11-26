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
