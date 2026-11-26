import os
import re
import shutil
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core.auth import project_dir
from app.core.config import settings


class PurgeRequest(BaseModel):
    scope: Literal["temp", "proxies", "exports", "all_cache"]
    project_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")


def measure(root):
    total = 0
    for directory, _, files in os.walk(root):
        for name in files:
            path = Path(directory) / name
            try:
                if not path.is_symlink():
                    total += path.stat().st_size
            except FileNotFoundError:
                continue
    return total


def storage():
    root = settings().workspace_dir
    breakdown = {}
    sizes = {"proxies_bytes": 0, "exports_bytes": 0, "pins_bytes": 0, "models_bytes": 0}
    total = 0
    for folder, _, files in os.walk(root):
        rel = Path(folder).relative_to(root).parts
        for name in files:
            path = Path(folder) / name
            try:
                size = 0 if path.is_symlink() else path.stat().st_size
            except FileNotFoundError:
                continue
            total += size
            if rel and re.fullmatch(r"[a-f0-9]{32}", rel[0]):
                breakdown[rel[0]] = breakdown.get(rel[0], 0) + size
                if len(rel) > 1 and rel[1] in ("proxies", "output", "pins"):
                    sizes[
                        {
                            "proxies": "proxies_bytes",
                            "output": "exports_bytes",
                            "pins": "pins_bytes",
                        }[rel[1]]
                    ] += size
            elif rel and rel[0] in ("models", ".models"):
                sizes["models_bytes"] += size
    limit = int(settings().disk_limit_gb * 1024**3)
    ratio = total / max(1, limit)
    return dict(
        disk_limit_bytes=limit,
        used_bytes=total,
        workspace_bytes=total,
        **sizes,
        usage_ratio=ratio,
        status="critical" if ratio >= 0.9 else "warning" if ratio >= 0.8 else "ok",
        project_breakdown=breakdown,
    )


def guard(incoming=0):
    stats = storage()
    if (stats["used_bytes"] + incoming) >= 0.9 * stats["disk_limit_bytes"]:
        raise HTTPException(507, "工作区将达到磁盘配额的 90%，请先清理代理或导出缓存")


def purge_project(pid, scope):
    root = project_dir(pid)
    paths = []
    if scope in ("proxies", "all_cache"):
        paths.append(root / "proxies")
    if scope in ("temp", "all_cache"):
        paths.extend([root / "previews", root / ".tmp", root / "cache"])
        for directory in ("assets", "media", "proxies"):
            folder = root / directory
            if not folder.is_symlink():
                paths.extend(folder.glob("*.tmp"))
                paths.extend(folder.glob("*.tmp.mp4"))
        output = root / "output"
        if not output.is_symlink():
            paths.extend(output.glob("_tmp*"))
    if scope == "exports":
        paths.append(root / "output")
    freed = 0
    for path in paths:
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            freed += measure(path)
            shutil.rmtree(path)
        elif path.is_file():
            freed += path.stat().st_size
            path.unlink()
    return freed
