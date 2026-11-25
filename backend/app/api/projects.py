from fastapi import APIRouter, HTTPException

from app.db import repository as repo
from app.pipeline.orchestrator import read
from app.schemas.project import Project, ProjectCreate

router = APIRouter(prefix="/api/projects")


async def get(pid):
    try:
        return await repo.project(pid)
    except KeyError:
        raise HTTPException(404, "项目不存在")


@router.post("", response_model=Project, status_code=201)
async def create(data: ProjectCreate):
    return await repo.create(data)


@router.get("", response_model=list[Project])
async def projects():
    return await repo.projects()


@router.get("/{pid}")
async def detail(pid: str):
    logs = await repo.logs(pid)
    p = await get(pid)
    return dict(
        **p,
        research=read(pid, "research"),
        fact_check=read(pid, "fact_check"),
        scenes=await repo.scenes(pid),
        sources=await repo.sources(pid),
        stage_runs=await repo.runs(pid),
        logs=logs,
    )
