from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings
from app.schemas.timeline import Aspect


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
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class MediaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transition: Literal[
        "fade", "slideleft", "wipeleft", "slideup", "smoothleft", "none"
    ] = "fade"
    subtitle_style: Literal["pill_dark", "clean_stroke", "highlight_bar"] = "pill_dark"
    speech_rate: Literal["-10%", "+0%", "+10%", "+20%"] = "+0%"


class ProjectCreate(MediaSettings):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    topic: str = Field(min_length=1, max_length=240)
    target_format: FormatType = FormatType.landscape
    skill_id: str | None = None
    aspect_ratio: Aspect | None = None
    theme: Literal["editorial_dark", "clean_light", "warm_amber"] = "editorial_dark"
    voice: str = Field(default="", max_length=100)
    brand_label: str = Field(default="", max_length=32)
    execution_mode: Literal["api", "agent_cli", "mcp"] = Field(
        default_factory=lambda: settings().default_execution_mode
    )
    seed_materials: str = Field(default="", max_length=64000)
    seed_only: bool = False
    auto_approve: bool = False

    @model_validator(mode="after")
    def has_materials(self):
        if self.seed_only and not self.seed_materials.strip():
            raise ValueError("仅使用自带资料时需要填写参考资料")
        return self


class Project(ProjectCreate):
    id: str
    status: ProjectStatus
    fact_check_loops: int
    total_tokens: int
    estimated_cost_cny: float
    error_message: str | None
    created_at: str
    updated_at: str
    timeline_revision: int | None = None
