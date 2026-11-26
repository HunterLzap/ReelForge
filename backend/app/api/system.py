import asyncio
import shutil
import sys

from fastapi import APIRouter

from app.api.external import idle
from app.api.pipeline import locks
from app.api.projects import get
from app.core.config import ROOT, settings
from app.core.llm_client import cli_args
from app.db import repository as repo
from app.media.limits import project_files
from app.services import storage_manager

router = APIRouter()


@router.get("/api/system/engines")
def engines():
    cfg = settings()
    args = cli_args(cfg)
    detected = [name for name in ("codex", "claude") if shutil.which(name)]
    if cfg.agent_cli_preset == "custom" and args and shutil.which(args[0]):
        detected.append("custom")
    key = cfg.llm_api_key.strip().lower()
    return {
        "mock_llm": cfg.mock_llm,
        "api_configured": bool(
            key and key not in {"your_api_key_here", "changeme", "sk-xxx"}
        ),
        "model": cfg.llm_model,
        "available_clis": detected,
        "preset": cfg.agent_cli_preset,
        "default_execution_mode": cfg.default_execution_mode,
        "mcp_config": {
            "mcpServers": {
                "reelforge": {
                    "command": sys.executable,
                    "env": {
                        "PYTHONPATH": str(ROOT / "backend"),
                        "REELFORGE_API_BASE": cfg.reelforge_api_base,
                    },
                    "args": ["-m", "app.mcp_server"],
                }
            }
        },
    }


@router.get("/api/system/health")
def health():
    return {"status": "ok"}


@router.get("/api/system/storage")
def storage_usage():
    return storage_manager.storage()


@router.post("/api/system/storage/purge")
async def purge(body: storage_manager.PurgeRequest):
    projects = (
        [await get(body.project_id)] if body.project_id else await repo.projects()
    )
    freed = 0
    for project in projects:
        pid = project["id"]
        async with locks[pid], project_files(pid):
            await idle(pid)
            freed += await asyncio.to_thread(
                storage_manager.purge_project, pid, body.scope
            )
            if body.scope in ("all_cache", "proxies"):
                await repo.execute(
                    "UPDATE media_assets SET proxy_rel_path=NULL WHERE project_id=?",
                    pid,
                )
    return {"freed_bytes": freed}


@router.post("/api/system/probe")
async def probe():
    from app.services.model_manager import probe_hardware

    return await probe_hardware()
