from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FormatType(StrEnum):
    landscape = "video_16_9"
    portrait = "video_9_16"
    cards = "cards_3_4"


class ProjectStatus(StrEnum):
    PENDING = "PENDING"
    RESEARCHING = "RESEARCHING"
    FACT_CHECKING = "FACT_CHECKING"
    WAITING_OUTLINE = "WAITING_OUTLINE"
    DIRECTING = "DIRECTING"
    WAITING_STORYBOARD = "WAITING_STORYBOARD"
    RENDERING = "RENDERING"
    ASSEMBLING = "ASSEMBLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    topic: str = Field(min_length=1, max_length=240)
    target_format: FormatType = FormatType.landscape
    theme: Literal["editorial_dark", "clean_light", "warm_amber"] = "editorial_dark"
    voice: str = Field(default="", max_length=100)
    brand_label: str = Field(default="", max_length=32)
    transition: Literal["fade", "slideleft"] = "fade"
    auto_approve: bool = False


class Project(ProjectCreate):
    id: str
    status: ProjectStatus
    fact_check_loops: int
    total_tokens: int
    estimated_cost_cny: float
    error_message: str | None
    created_at: str
    updated_at: str
