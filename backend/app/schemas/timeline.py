from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

Track = Literal["video", "overlay", "annotation", "subtitle", "audio"]
Aspect = Literal["16:9", "9:16", "1:1", "3:4"]
SIZES = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "3:4": (1080, 1440),
}
FORMATS = {
    "video_16_9": "16:9",
    "video_9_16": "9:16",
    "cards_3_4": "3:4",
    "video_1_1": "1:1",
}


class Clip(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    kind: str = Field(min_length=1)
    start_ms: int = Field(default=0, ge=0)
    end_ms: int = Field(gt=0)
    source_in_ms: int = Field(default=0, ge=0)
    source_out_ms: int | None = Field(default=None, gt=0)
    speed: float = Field(default=1, gt=0, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def timing(cls, data):
        values = dict(data)
        duration = values.pop("duration_ms", None)
        if "end_ms" not in values:
            if (
                duration is None
                and values.get("source_out_ms") is not None
                and values.get("speed", 1) > 0
            ):
                duration = round(
                    (values["source_out_ms"] - values.get("source_in_ms", 0))
                    / values.get("speed", 1)
                )
            if duration is not None:
                values["end_ms"] = values.get("start_ms", 0) + duration
        return values

    @model_validator(mode="after")
    def bounds(self):
        if self.end_ms <= self.start_ms or (
            self.source_out_ms is not None and self.source_out_ms <= self.source_in_ms
        ):
            raise ValueError("片段时长必须大于零")
        return self


class Tracks(BaseModel):
    video: list[Clip] = Field(
        default_factory=list, validation_alias=AliasChoices("video", "main_video")
    )
    overlay: list[Clip] = []
    annotation: list[Clip] = []
    subtitle: list[Clip] = []
    audio: list[Clip] = []

    @model_validator(mode="before")
    @classmethod
    def sequential(cls, data):
        values = dict(data)
        key = "main_video" if "main_video" in values else "video"
        pos = 0
        clips = []
        for item in values.get(key, []):
            if isinstance(item, dict):
                item = Clip.model_validate({"start_ms": pos, **item})
            clips.append(item)
            pos = item.end_ms
        values[key] = clips
        values["subtitle"] = [
            {"kind": "subtitle", **c} if isinstance(c, dict) else c
            for c in values.get("subtitle", [])
        ]
        return values

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [
            clip.id
            for track in type(self).model_fields
            for clip in getattr(self, track)
        ]
        if len(set(ids)) != len(ids):
            raise ValueError("片段 ID 必须唯一")
        return self


class Resolution(BaseModel):
    width: int = Field(gt=0, le=7680)
    height: int = Field(gt=0, le=7680)


class TimelineDocument(BaseModel):
    version: Literal["3.0"] = "3.0"
    project_id: str
    revision: int = Field(0, ge=0)
    fps: int = Field(30, gt=0, le=120)
    aspect_ratio: Aspect = "16:9"
    resolution: Resolution
    skill_id: str = "motion-editorial"
    theme: str = "editorial_dark"
    tracks: Tracks = Field(default_factory=Tracks)
    bgm: dict | None = None
    subtitle_style: dict | str = "pill_dark"
    export: dict = {}
    meta: dict = {}

    @model_validator(mode="before")
    @classmethod
    def format_defaults(cls, data):
        values = dict(data)
        aspect = values.setdefault(
            "aspect_ratio", FORMATS.get(values.get("format"), "16:9")
        )
        if aspect in SIZES:
            w, h = SIZES[aspect]
            values.setdefault("resolution", {"width": w, "height": h})
        return values


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OnTrack(Operation):
    track: Track = "video"


class AddClip(OnTrack):
    op: Literal["add_clip", "insert_clip"]
    clip: dict
    index: int | None = Field(None, ge=0)


class Target(OnTrack):
    clip_id: str


class UpdateClip(Target):
    op: Literal["update_clip"]
    patch: dict = Field(validation_alias=AliasChoices("patch", "changes", "fields", "updates"))


class DeleteClip(Target):
    op: Literal["delete_clip"]


class SplitClip(Target):
    op: Literal["split_clip"]
    at_ms: int = Field(ge=0, validation_alias=AliasChoices("at_ms", "split_at_ms"))


class RippleDelete(Operation):
    op: Literal["ripple_delete"]
    track: Track | Literal["all"] = "video"
    tracks: list[Track] | None = None
    clip_id: str | None = None
    start_ms: int | None = Field(None, ge=0)
    end_ms: int | None = Field(None, gt=0)


class Reorder(Target):
    op: Literal["reorder"]
    target_index: int = Field(ge=0)


class SetBgm(Operation):
    op: Literal["set_bgm"]
    bgm: dict | None = Field(validation_alias=AliasChoices("bgm", "value"))


class SetSubtitleStyle(Operation):
    op: Literal["set_subtitle_style"]
    subtitle_style: dict | str = Field(
        validation_alias=AliasChoices("subtitle_style", "style", "value")
    )


class SetExportSpec(Operation):
    op: Literal["set_export_spec"]
    export: dict = Field(
        validation_alias=AliasChoices("export", "spec", "value", "export_spec")
    )


TimelineOp = Annotated[
    AddClip
    | UpdateClip
    | DeleteClip
    | SplitClip
    | RippleDelete
    | Reorder
    | SetBgm
    | SetSubtitleStyle
    | SetExportSpec,
    Field(discriminator="op"),
]


class TimelinePatchRequest(BaseModel):
    base_revision: int = Field(ge=0)
    author: str = Field("user", validation_alias=AliasChoices("author", "actor"))
    summary: str = "编辑时间轴"
    review_pin_id: str | None = None
    ops: list[TimelineOp] = Field(min_length=1)
