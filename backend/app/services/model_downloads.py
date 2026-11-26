"""Stream model files into resumable partials. Only publish completed files."""

import asyncio
import json
import re
from contextlib import suppress
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.core.events import notify, subscribe
from app.services.model_manager import CATALOG, guard_size, model_directory
from app.services.storage_manager import guard

jobs = {}
workers = {}


def listing():
    root = settings().workspace_dir
    return [
        state for (workspace, _), state in reversed(jobs.items()) if workspace == root
    ]


def channel():
    return ("model_downloads", settings().workspace_dir)


async def events(request):
    with subscribe(channel()) as signal:
        while not await request.is_disconnected():
            signal.clear()
            yield "data: " + json.dumps(listing(), ensure_ascii=False) + "\n\n"
            try:
                await asyncio.wait_for(signal.wait(), 15)
            except TimeoutError:
                yield ": heartbeat\n\n"


def progress(state, done, total):
    state.update(
        downloaded_bytes=done,
        total_bytes=total,
        percentage=min(99, round(100 * done / max(1, total), 1)),
    )
    notify(channel())


async def simulate(folder, state):
    # Persist a small deterministic fixture, separate from usable model weights.
    path = folder / ".mock.part"
    total = 65536
    with path.open("ab") as out:
        progress(state, out.tell(), total)
        while out.tell() < total:
            await asyncio.sleep(0.04)
            out.write(bytes(4096))
            out.flush()
            progress(state, out.tell(), total)
    path.replace(folder / ".mock.complete")


async def pull_ollama(client, entry, state):
    totals, completed = {}, {}
    async with client.stream(
        "POST", "http://127.0.0.1:11434/api/pull", json={"model": entry["ollama"]}
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            item = json.loads(line)
            if item.get("error"):
                raise ValueError(item["error"])
            if item.get("status") == "success":
                return
            if digest := item.get("digest"):
                totals[digest] = item.get("total", totals.get(digest, 0))
                completed[digest] = item.get("completed", completed.get(digest, 0))
                progress(state, sum(completed.values()), sum(totals.values()))
    raise ValueError("Ollama 下载未完成")


async def fetch_files(client, entry, folder, state):
    host = (
        "https://hf-mirror.com"
        if state["mirror"] == "hf-mirror"
        else "https://modelscope.cn/models"
    )
    urls = {
        name: f"{host}/{entry['repo']}/resolve/{'main' if state['mirror'] == 'hf-mirror' else 'master'}/{name}"
        for name in entry["files"]
    }
    sizes = {}
    for name, url in urls.items():
        async with client.stream("GET", url, headers={"Range": "bytes=0-0"}) as head:
            head.raise_for_status()
            size = head.headers.get("content-range", "").split("/")[
                -1
            ] or head.headers.get("content-length", "")
            if not size.isdigit() or int(size) <= 0:
                raise ValueError("镜像未提供文件大小")
            sizes[name] = int(size)
    total = sum(sizes.values())
    guard_size(total / 1_000_000)
    await asyncio.to_thread(
        guard,
        max(0, total - sum(p.stat().st_size for p in folder.iterdir() if p.is_file())),
    )
    done = 0
    for name, url in urls.items():
        dest = folder / name
        size = sizes[name]
        if dest.is_file() and dest.stat().st_size == size:
            done += size
            continue
        part = folder / (name + ".part")
        offset = part.stat().st_size if part.exists() else 0
        if offset != size:
            async with client.stream(
                "GET",
                url,
                headers={"Range": f"bytes={offset}-"} if 0 < offset < size else {},
            ) as res:
                res.raise_for_status()
                append = bool(res.headers.get("content-range"))
                if append and not re.fullmatch(
                    rf"bytes {offset}-{size - 1}/{size}",
                    res.headers.get("content-range", ""),
                ):
                    raise ValueError("镜像断点范围不一致")
                with part.open("ab" if append else "wb") as out:
                    async for chunk in res.aiter_bytes(256 * 1024):
                        if out.tell() + len(chunk) > size:
                            raise ValueError("镜像文件超过声明大小")
                        out.write(chunk)
                        progress(state, done + out.tell(), total)
        if part.stat().st_size != size:
            raise ValueError("镜像传输中断，可重新下载以续传")
        part.replace(dest)
        done += size
    progress(state, done, total)


async def run(key, state, entry, folder, mock):
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if mock:
            await simulate(folder, state)
        else:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60, connect=5),
                follow_redirects=True,
                trust_env=state["mirror"] != "ollama",
            ) as client:
                if state["mirror"] == "ollama":
                    await pull_ollama(client, entry, state)
                else:
                    await fetch_files(client, entry, folder, state)
            (folder / ".complete").write_text(state["mirror"])
        state.update(status="completed", percentage=100)
    except asyncio.CancelledError:
        state.update(status="cancelled")
        raise
    except (OSError, httpx.HTTPError, ValueError, HTTPException) as exc:
        state.update(status="failed", error=str(exc))
    finally:
        workers.pop(key, None)
        notify(channel())


async def start(body):
    entry = CATALOG.get(body.model)
    if not entry:
        raise HTTPException(422, "模型不在下载目录")
    guard_size(max(body.model_size_mb, entry["size_mb"]))
    if body.mirror not in entry["mirrors"]:
        raise HTTPException(422, "该模型未发布到所选镜像")
    for state in listing():
        if state["model"] == body.model and state["status"] == "downloading":
            return state
    task_id = uuid4().hex
    key = (settings().workspace_dir, task_id)
    state = {
        "task_id": task_id,
        "model": body.model,
        "mirror": body.mirror,
        "status": "downloading",
        "downloaded_bytes": 0,
        "total_bytes": entry["size_mb"] * 1_000_000,
        "percentage": 0,
        "mock": settings().mock_llm,
    }
    jobs[key] = state
    notify(channel())
    workers[key] = asyncio.create_task(
        run(key, state, entry, model_directory(body.model), settings().mock_llm)
    )
    return state


async def cancel(task_id):
    key = (settings().workspace_dir, task_id)
    if key not in jobs:
        raise HTTPException(404, "下载任务不存在")
    if task := workers.get(key):
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        jobs[key]["status"] = "cancelled"
        notify(channel())
        workers.pop(key, None)
    return jobs[key]
