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


async def emit(pid, stage, message, level="info"):
    await repo.log(pid, stage, message, level)
    for signal in listeners.get(pid, ()):
        signal.set()
