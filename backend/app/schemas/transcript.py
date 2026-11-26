from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.timeline import TimelineDocument


class WordToken(BaseModel):
    id: str
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    tag: Literal["normal", "filler", "pause"] = "normal"
    deleted: bool = False


class TranscriptSegment(BaseModel):
    id: str
    text: str
    start_ms: int
    end_ms: int
    words: list[WordToken]


class TranscriptDocument(BaseModel):
    asset_id: str
    engine: str
    language: str = "zh"
    hotwords: list[str] = []
    segments: list[TranscriptSegment]
    silences: list[tuple[int, int]] = []


class RoughCutIssue(BaseModel):
    id: str
    kind: Literal["silence", "filler", "retake"]
    start_ms: int
    end_ms: int
    text: str
    word_ids: list[str] = []


class RoughCutRequest(BaseModel):
    base_revision: int | None = Field(None, ge=0)
    apply: bool = False
    issue_ids: list[str] | None = None
    buffer_ms: int = Field(80, ge=0, le=2000)
    delete_word_ids: list[str] | None = None
    cut_ranges_ms: list[tuple[int, int]] | None = None

    @model_validator(mode="after")
    def ranges(self):
        if (
            sum(
                v is not None
                for v in [self.issue_ids, self.delete_word_ids, self.cut_ranges_ms]
            )
            > 1
        ):
            raise ValueError("每次仅选择一种剪辑方式")
        if any(a < 0 or b <= a for a, b in self.cut_ranges_ms or []):
            raise ValueError("无效的剪辑范围")
        return self


class RoughCutPreview(BaseModel):
    issues: list[RoughCutIssue]
    saved_ms: int
    base_revision: int
    cut_ranges_ms: list[tuple[int, int]]
    timeline: TimelineDocument | None = None
