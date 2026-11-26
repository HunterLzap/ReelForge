"""Shared heavy-work slots. File locks also coordinate headless MCP on macOS/Linux."""

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from hashlib import sha256
from weakref import WeakKeyDictionary, WeakValueDictionary

from app.core.config import settings

_gates = WeakKeyDictionary()


def project_files(pid):
    # Use one stable lock for publication, cache cleanup and removal of a project.
    name = sha256(pid.encode()).hexdigest()
    return _slot("project-" + name, 1)


def slot(kind):
    cfg = settings()
    limit = (
        cfg.effective_render_concurrency()
        if kind == "render"
        else cfg.effective_browser_concurrency()
    )
    return _slot(kind, limit)


@asynccontextmanager
async def _slot(kind, limit):
    cfg = settings()
    gates = _gates.setdefault(asyncio.get_running_loop(), WeakValueDictionary())
    key = (cfg.workspace_dir, kind, limit)
    gate = gates.get(key)
    if gate is None:
        gate = gates[key] = asyncio.Semaphore(limit)
    async with gate, AsyncExitStack() as stack:
        if os.name == "posix":
            import fcntl

            directory = cfg.workspace_dir / ".locks"
            directory.mkdir(parents=True, exist_ok=True)
            while True:
                for index in range(limit):
                    lock = (directory / f"{kind}-{index}").open("a")
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        lock.close()
                        continue
                    stack.callback(lock.close)
                    break
                else:
                    await asyncio.sleep(0.1)
                    continue
                break
        yield
