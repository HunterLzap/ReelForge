from pydantic import BaseModel, Field, HttpUrl


class SourceItem(BaseModel):
    id: str
    title: str
    url: HttpUrl
    snippet: str
    credibility_note: str


class ResearchPack(BaseModel):
    outline: list[str] = Field(min_length=1)
    sources: list[SourceItem] = Field(min_length=1)


class FactCheckReport(BaseModel):
    approved: bool
    summary: str
    issues: list[str]
