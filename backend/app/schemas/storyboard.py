from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]


Heading = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=36)
]
Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=24)
]
Badge = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)
]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cover(Payload):
    title: Heading
    subtitle: Text
    tag: Badge


class Quote(Payload):
    quote: Text
    highlight: Label
    attribution: Label


class ListPoint(Payload):
    label: Label
    desc: Text


class Bullet(Payload):
    heading: Heading
    items: list[ListPoint] = Field(min_length=3, max_length=4)


class Bar(Payload):
    label: Label
    value: float = Field(allow_inf_nan=False)
    accent: str = Field(pattern="^#[0-9a-fA-F]{6}$")


class Chart(Payload):
    heading: Heading
    unit: Badge
    bars: list[Bar] = Field(min_length=3, max_length=5)
    takeaway: Text


class Compare(Payload):
    heading: Heading
    left_title: Label
    left_points: list[Text] = Field(min_length=1, max_length=4)
    right_title: Label
    right_points: list[Text] = Field(min_length=1, max_length=4)


class Step(Payload):
    step_label: Badge
    title: Heading
    desc: Text


class Timeline(Payload):
    heading: Heading
    steps: list[Step] = Field(min_length=3, max_length=4)


class SceneBase(Payload):
    narration: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=460)
    ]
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


class Hero(Payload):
    metric: Badge
    unit: Badge
    label: Label
    context: Text
    delta: Text


class Check(Payload):
    status: Literal["do", "dont"]
    title: Heading
    detail: Text


class Checklist(Payload):
    heading: Heading
    items: list[Check] = Field(min_length=2, max_length=4)


class HeroScene(SceneBase):
    template_type: Literal["hero_stat"]
    visual_payload: Hero


class ChecklistScene(SceneBase):
    template_type: Literal["checklist"]
    visual_payload: Checklist


SceneItem = Annotated[
    CoverScene
    | QuoteScene
    | BulletScene
    | ChartScene
    | CompareScene
    | TimelineScene
    | HeroScene
    | ChecklistScene,
    Field(discriminator="template_type"),
]


class StoryboardScript(BaseModel):
    scenes: list[SceneItem] = Field(min_length=1)

    @model_validator(mode="after")
    def first_cover(self):
        if [i for i, s in enumerate(self.scenes) if s.template_type == "cover"] != [0]:
            raise ValueError("封面必须且只能位于第一幕")
        return self
