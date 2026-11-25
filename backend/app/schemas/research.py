from pydantic import BaseModel, Field, HttpUrl


class SourceItem(BaseModel):
    id: str
    title: str
    url: HttpUrl
    snippet: str
    credibility_note: str


class Evidence(BaseModel):
    claim: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class ResearchPack(BaseModel):
    key_facts: list[Evidence] = Field(default_factory=list)
    data_points: list[Evidence] = Field(default_factory=list)
    outline: list[str] = Field(min_length=1)
    sources: list[SourceItem] = Field(min_length=1)


class FactCheckReport(BaseModel):
    follow_up_queries: list[str] = Field(default_factory=list)
    checks: list[dict[str, str]] = Field(default_factory=list)
    approved: bool
    summary: str
    issues: list[str]
