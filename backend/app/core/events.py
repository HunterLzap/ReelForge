import asyncio
from collections import defaultdict
from contextlib import contextmanager

from app.db import repository as repo

listeners = defaultdict(set)


@contextmanager
def subscribe(pid):
    signal = asyncio.Event()
    listeners[pid].add(signal)
    try:
        yield signal
    finally:
        listeners[pid].discard(signal)
        if not listeners[pid]:
            del listeners[pid]


async def record(db, pid, stage, **payload):
    """Persist an editor event alongside its mutation; notify after commit."""
    await db.execute(
        "INSERT INTO event_logs(project_id,level,stage_name,message) VALUES(?,'info',?,?)",
        (pid, stage, repo.dump(payload)),
    )


async def emit(pid, stage, message, level="info"):
    await repo.log(pid, stage, message, level)
    notify(pid)


def notify(pid):
    for signal in listeners.get(pid, ()):
        signal.set()
