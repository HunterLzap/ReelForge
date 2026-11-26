import shutil
import sys

from fastapi import APIRouter

from app.core.config import settings
from app.core.llm_client import cli_args

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
                    "args": ["-m", "app.mcp_server"],
                }
            }
        },
    }
