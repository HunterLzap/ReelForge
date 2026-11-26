import asyncio
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api import (
    assets,
    external,
    media,
    models,
    pipeline,
    projects,
    review_pins,
    scenes,
    skills,
    stream,
    system,
    timelines,
    transcripts,
)
from app.core.auth import UnsafePath, authenticate
from app.core.config import settings
from app.db.database import init
from app.media.renderer import previews
from app.services.uploads import UploadGuard


@asynccontextmanager
async def lifespan(app):
    await init()
    yield
    await asyncio.gather(*list(pipeline.tasks.values()), return_exceptions=True)
    await previews.close()


class ProjectMedia(StaticFiles):
    def lookup_path(self, path):
        # Resolve against the active workspace, including isolated headless sessions.
        root = settings().workspace_dir
        candidate = root / path
        if candidate.resolve() != candidate:
            return "", None
        try:
            return str(candidate), candidate.stat()
        except (FileNotFoundError, NotADirectoryError):
            return "", None

    async def get_response(self, path, scope):
        if not re.fullmatch(
            r"[0-9a-f]{32}/(?:pins/[0-9a-f]{32}\.png|media/[0-9a-f]{32}\.(?:mp4|mov|webm|mp3|wav|m4a|png|jpg|jpeg|webp)|proxies/[0-9a-f]{32}\.mp4|assets/[0-9a-f]{64}\.(?:png|jpg|webp)|output/(?:final\.mp4|sources\.md|cards\.zip|cards/\d+\.png)|scenes/[0-9a-f]{32}/(?:card\.png|audio\.mp3))",
            path.replace("\\", "/"),
        ):
            raise HTTPException(404)
        return await super().get_response(path, scope)


app = FastAPI(title="ReelForge", lifespan=lifespan)
app.add_middleware(UploadGuard)
app.middleware("http")(authenticate)
app.add_exception_handler(timelines.RevisionConflict, timelines.conflict_handler)


@app.exception_handler(UnsafePath)
async def unsafe_path(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


for module in (
    projects,
    pipeline,
    scenes,
    stream,
    external,
    system,
    assets,
    media,
    models,
    transcripts,
    skills,
    timelines,
    review_pins,
):
    app.include_router(module.router)
app.mount(
    "/workspace",
    ProjectMedia(directory=settings().workspace_dir, check_dir=False),
    name="workspace",
)
