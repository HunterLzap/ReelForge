import asyncio
from contextlib import suppress
from weakref import WeakValueDictionary

from fastapi import APIRouter, HTTPException

from app.api.projects import get
from app.db import repository as repo
from app.pipeline import orchestrator

router = APIRouter(prefix="/api/projects")
tasks = {}


class ProjectLocks(WeakValueDictionary):
    def __getitem__(self, pid):
        lock = self.get(pid)
        if lock is None:
            lock = asyncio.Lock()
            self[pid] = lock
        return lock


locks = ProjectLocks()


def finished(pid, task):
    if tasks.get(pid) is task:
        tasks.pop(pid, None)
    if not task.cancelled():
        task.exception()  # Orchestrator persists the failure and emits it to subscribers.


async def schedule(pid, action):
    async with locks[pid]:
        p = await get(pid)
        if pid in tasks and not tasks[pid].done():
            raise HTTPException(409, "项目正在运行")
        allowed = {
            "approve": {"WAITING_OUTLINE", "WAITING_STORYBOARD"},
            "rebuild": {"COMPLETED"},
            "render": {"COMPLETED", "WAITING_STORYBOARD", "FAILED", "CANCELLED"},
            "run": {
                "PENDING",
                "CANCELLED",
                "FAILED",
                "RESEARCHING",
                "FACT_CHECKING",
                "DIRECTING",
                "RENDERING",
                "ASSEMBLING",
            },
        }
        if p["execution_mode"] == "mcp" and (
            action == "run"
            or (action == "approve" and p["status"] == "WAITING_OUTLINE")
        ):
            raise HTTPException(409, "请通过外部 Agent 写入资料和分镜")
        if p["status"] not in allowed[action]:
            raise HTTPException(409, "当前状态不支持此操作")
        if (
            action == "approve"
            and p["status"] == "WAITING_OUTLINE"
            and not orchestrator.read(pid, "fact_check")
        ):
            raise HTTPException(409, "外部资料已就绪，请通过外部 Agent 写入分镜")
        if action == "render" and not await repo.scenes(pid):
            raise HTTPException(409, "请先写入分镜")
        task = asyncio.create_task(
            orchestrator.run(pid, "rebuild" if action == "render" else action)
        )
        tasks[pid] = task
        task.add_done_callback(lambda t: finished(pid, t))
        return task


async def start(pid, action):
    await schedule(pid, action)
    return {"accepted": True}


@router.post("/{pid}/run", status_code=202)
async def run(pid: str):
    return await start(pid, "run")


@router.post("/{pid}/approve", status_code=202)
async def approve(pid: str):
    return await start(pid, "approve")


@router.post("/{pid}/rebuild", status_code=202)
async def rebuild(pid: str):
    return await start(pid, "rebuild")


@router.post("/{pid}/cancel")
async def cancel(pid: str):
    async with locks[pid]:
        await get(pid)
        task = tasks.get(pid)
        if task is None or task.done():
            raise HTTPException(409, "项目当前没有运行中的任务")
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        finished(pid, task)
        await orchestrator.state(pid, "CANCELLED", "用户已中止任务")
        return {"status": "CANCELLED"}


@router.patch("/{pid}/scenes/{sid}")
async def edit(pid: str, sid: str, changes: dict):
    async with locks[pid]:
        p = await get(pid)
        if pid in tasks or p["status"] not in ("COMPLETED", "WAITING_STORYBOARD"):
            raise HTTPException(409, "当前状态不支持编辑")
        try:
            await orchestrator.edit(pid, sid, changes)
        except KeyError:
            raise HTTPException(404, "分镜不存在")
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return {"render_status": "DIRTY"}
