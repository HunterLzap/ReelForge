from typing import Literal

from pydantic import AliasChoices, BaseModel, Field


class MediaAsset(BaseModel):
    id: str
    project_id: str
    kind: Literal["video", "image", "audio"]
    filename: str
    path: str = Field(validation_alias=AliasChoices("path", "rel_path"))
    proxy_path: str | None = Field(
        validation_alias=AliasChoices("proxy_path", "proxy_rel_path")
    )
    duration_ms: int | None
    width: int | None
    height: int | None
    fps: float | None
    size_bytes: int
    sha256: str
    source_type: str
    source_url: str | None
    license: str | None
    mime_type: str
    created_at: str
