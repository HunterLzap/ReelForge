from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.timeline import Aspect


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(
        "",
        validation_alias=AliasChoices(
            "path", "root", "root_path", "library_root", "directory"
        ),
    )
    aspect: Aspect | None = Field(
        None, validation_alias=AliasChoices("aspect", "aspect_ratio")
    )


class LibraryItem(BaseModel):
    id: str
    rel_path: str
    filename: str
    kind: Literal["video", "audio", "image"]
    sha256: str
    size_bytes: int
    duration_ms: int | None
    width: int | None
    height: int | None
    fps: float | None
    caption: str
    tags: list[str]
    quality_flags: list[str]
    keyframes: list[str]
    thumbnail_url: str | None
