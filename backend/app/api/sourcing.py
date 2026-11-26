from typing import Literal

from fastapi import APIRouter
from pydantic import AliasChoices, BaseModel, Field, HttpUrl, model_validator

from app.api.projects import get
from app.media.assets import LIMIT
from app.schemas.timeline import Track
from app.services import web_sourcing

router = APIRouter(prefix="/api/projects/{pid}")


class Search(BaseModel):
    q: str = Field(
        min_length=1, max_length=500, validation_alias=AliasChoices("q", "query")
    )
    kind: Literal["all", "article", "image", "video"] = "all"


class Fetch(BaseModel):
    url: HttpUrl
    media_url: HttpUrl | None = None
    license: str | None = None
    use_browser: bool | None = None


class Paste(BaseModel):
    image_data_url: str | None = Field(None, max_length=(LIMIT + 2) // 3 * 4 + 64)
    url: HttpUrl | None = None
    filename: str | None = Field(None, max_length=255)
    slot_clip_id: str | None = None
    track: Track = "video"
    base_revision: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.image_data_url) == bool(self.url):
            raise ValueError("请选择一张图片或一个 URL")
        return self


@router.post("/sourcing/search")
async def search(pid: str, body: Search):
    await get(pid)
    return {"results": await web_sourcing.search(body.q, body.kind)}


@router.post("/sourcing/fetch")
async def fetch(pid: str, body: Fetch):
    return await web_sourcing.fetch(pid, **body.model_dump(mode="json"))


@router.post("/sourcing/paste")
async def paste(pid: str, body: Paste):
    return await web_sourcing.paste(pid, body)


@router.post("/library/{item_id}/import")
async def import_item(pid: str, item_id: str):
    return await web_sourcing.attach_library(pid, item_id)
