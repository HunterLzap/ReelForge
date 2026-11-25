import asyncio
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from app.api.projects import get
from app.pipeline import orchestrator

router = APIRouter(prefix="/api/projects")
tasks = {}
locks = defaultdict(asyncio.Lock)


def finished(pid, task):
    if tasks.get(pid) is task:
        tasks.pop(pid, None)
    if not task.cancelled():
        task.exception()  # Orchestrator persists the failure and emits it to subscribers.


async def start(pid, action):
    async with locks[pid]:
        p = await get(pid)
        if pid in tasks and not tasks[pid].done():
            raise HTTPException(409, "项目正在运行")
        allowed = {
            "approve": {"WAITING_OUTLINE", "WAITING_STORYBOARD"},
            "rebuild": {"COMPLETED"},
            "run": {
                "PENDING",
                "FAILED",
                "RESEARCHING",
                "FACT_CHECKING",
                "DIRECTING",
                "RENDERING",
                "ASSEMBLING",
            },
        }
        if p["status"] not in allowed[action]:
            raise HTTPException(409, "当前状态不支持此操作")
        task = asyncio.create_task(orchestrator.run(pid, action))
        tasks[pid] = task
        task.add_done_callback(lambda t: finished(pid, t))
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
