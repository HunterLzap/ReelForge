from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

from app.schemas.timeline import Track


class BBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def fits(self):
        if self.x + self.w > 1.000001 or self.y + self.h > 1.000001:
            raise ValueError("框选范围超出画布")
        return self


Status = Literal["open", "resolved", "dismissed"]


class PinFields(BaseModel):
    time_ms: int = Field(ge=0, validation_alias=AliasChoices("time_ms", "timestamp_ms"))
    bbox: BBox | None = None
    note: str = Field(
        min_length=1, max_length=8000, validation_alias=AliasChoices("note", "comment")
    )
    track: Track | None = Field(
        None, validation_alias=AliasChoices("track", "target_track")
    )
    clip_id: str | None = Field(
        None, validation_alias=AliasChoices("clip_id", "target_item_id")
    )


class PinCreate(PinFields):
    revision: int | None = Field(
        None, ge=0, validation_alias=AliasChoices("revision", "revision_id")
    )
    frame_data_url: str | None = Field(None, max_length=16 * 1024 * 1024)
    author: str = "user"


class ReviewPin(PinFields):
    id: str
    project_id: str
    revision: int
    frame_path: str
    frame_url: str
    status: Status
    resolved_by_revision: int | None
    created_at: str


class PinUpdate(BaseModel):
    status: Status | None = None
    note: str | None = Field(None, min_length=1, max_length=8000)
    resolved_by_revision: int | None = Field(None, ge=0)
