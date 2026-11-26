from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.timeline import Aspect

State = Literal["local_matched", "web_fetched", "motion_generated", "placeholder"]


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=6000)


class Brief(BaseModel):
    skill_id: str = "ai-news-montage"
    aspect_ratio: Aspect = "16:9"
    base_revision: int | None = Field(None, ge=0)


class Chat(Brief):
    message: str = Field(min_length=1, max_length=3000)
    history: list[Turn] = Field(default_factory=list, max_length=50)
    auto_apply: bool = False
    web_enabled: bool = True


class Shot(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    narration: str = Field(default="", max_length=1200)
    visual_query: str = Field(default="", max_length=500)
    duration_ms: int = Field(default=3000, ge=100, le=120000)
    source_state: State = "placeholder"
    asset_id: str | None = None
    source_url: str | None = None
    component_id: str | None = None
    props: dict = Field(default_factory=dict)
    placeholder_hint: str | None = None


class Plan(Brief):
    shots: list[Shot] = Field(min_length=1, max_length=60)
