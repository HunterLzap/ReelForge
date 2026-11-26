import asyncio
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api import assets, external, pipeline, projects, scenes, stream, system
from app.core.config import settings
from app.db.database import init
from app.media.renderer import previews


@asynccontextmanager
async def lifespan(app):
    await init()
    yield
    await asyncio.gather(*list(pipeline.tasks.values()), return_exceptions=True)
    await previews.close()


class ProjectMedia(StaticFiles):
    async def get_response(self, path, scope):
        if not re.fullmatch(
            r"[0-9a-f]{32}/(?:assets/[0-9a-f]{64}\.(?:png|jpg|webp)|output/(?:final\.mp4|sources\.md|cards\.zip|cards/\d+\.png)|scenes/[0-9a-f]{32}/(?:card\.png|audio\.mp3))",
            path.replace("\\", "/"),
        ):
            raise HTTPException(404)
        return await super().get_response(path, scope)


app = FastAPI(title="ReelForge", lifespan=lifespan)
for module in (projects, pipeline, scenes, stream, external, system, assets):
    app.include_router(module.router)
app.mount(
    "/workspace",
    ProjectMedia(directory=settings().workspace_dir, check_dir=False),
    name="workspace",
)
