from pydantic import BaseModel


class StageRun(BaseModel):
    id: int
    project_id: str
    stage_name: str
    attempt: int
    status: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    summary: str
    created_at: str


class SSEEvent(BaseModel):
    id: int
    project_id: str
    level: str
    stage_name: str
    message: str
    created_at: str
