from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cover(Payload):
    title: Text
    subtitle: Text
    tag: Text


class Quote(Payload):
    quote: Text
    highlight: Text
    attribution: Text


class ListPoint(Payload):
    label: Text
    desc: Text


class Bullet(Payload):
    heading: Text
    items: list[ListPoint] = Field(min_length=3, max_length=4)


class Bar(Payload):
    label: Text
    value: float = Field(allow_inf_nan=False)
    accent: str = Field(pattern="^#[0-9a-fA-F]{6}$")


class Chart(Payload):
    heading: Text
    unit: Text
    bars: list[Bar] = Field(min_length=3, max_length=5)
    takeaway: Text


class Compare(Payload):
    heading: Text
    left_title: Text
    left_points: list[Text] = Field(min_length=1)
    right_title: Text
    right_points: list[Text] = Field(min_length=1)


class Step(Payload):
    step_label: Text
    title: Text
    desc: Text


class Timeline(Payload):
    heading: Text
    steps: list[Step] = Field(min_length=3, max_length=4)


class SceneBase(Payload):
    narration: Text
    source_ids: list[str]


class CoverScene(SceneBase):
    template_type: Literal["cover"]
    visual_payload: Cover


class QuoteScene(SceneBase):
    template_type: Literal["big_quote"]
    visual_payload: Quote


class BulletScene(SceneBase):
    template_type: Literal["bullet_list"]
    visual_payload: Bullet


class ChartScene(SceneBase):
    template_type: Literal["stat_chart"]
    visual_payload: Chart


class CompareScene(SceneBase):
    template_type: Literal["compare_split"]
    visual_payload: Compare


class TimelineScene(SceneBase):
    template_type: Literal["timeline"]
    visual_payload: Timeline


SceneItem = Annotated[
    CoverScene | QuoteScene | BulletScene | ChartScene | CompareScene | TimelineScene,
    Field(discriminator="template_type"),
]


class StoryboardScript(BaseModel):
    scenes: list[SceneItem] = Field(min_length=1)

    @model_validator(mode="after")
    def first_cover(self):
        if [i for i, s in enumerate(self.scenes) if s.template_type == "cover"] != [0]:
            raise ValueError("封面必须且只能位于第一幕")
        return self
