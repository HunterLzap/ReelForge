from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.db import repository as repo
from app.pipeline.orchestrator import read
from app.schemas.project import FormatType, Project, ProjectCreate, ProjectStatus

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
async def projects(
    q: str = "",
    target_format: FormatType | None = None,
    status: ProjectStatus | None = None,
):
    return await repo.projects(q, target_format, status)


@router.get("/{pid}/publish-kit", response_class=PlainTextResponse)
async def publish_kit(pid: str):
    from app.pipeline.orchestrator import folder

    await get(pid)
    path = folder(pid) / "output/publish_kit.md"
    if not path.is_file():
        raise HTTPException(404, "尚未生成发布文案")
    return path.read_text(encoding="utf-8")


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
