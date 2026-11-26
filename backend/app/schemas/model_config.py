from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, HttpUrl, field_validator

Slot = Literal[
    "llm_director", "vlm_vision", "asr_speech", "tts_voice", "crawler_extract"
]
Mirror = Literal["hf-mirror", "modelscope", "ollama"]


class ModelConfig(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    base_url: str = ""
    api_key_env: str = Field(default="", pattern=r"^(?:[A-Z][A-Z0-9_]*(?:KEY|TOKEN))?$")
    enabled: bool = True
    extra: dict = {}
    model_size_mb: float = Field(0, ge=0, allow_inf_nan=False)

    @field_validator("base_url")
    @classmethod
    def http_endpoint(cls, value):
        if value:
            url = HttpUrl(value)
            if url.password or url.username or url.query or url.fragment:
                raise ValueError("Base URL 仅接受 HTTP(S) 服务地址")
        return value.rstrip("/")


class TestSlot(BaseModel):
    slot: Slot


class DownloadRequest(BaseModel):
    model: str = Field(validation_alias=AliasChoices("model", "model_id"))
    mirror: Mirror = "hf-mirror"
    model_size_mb: float = Field(0, ge=0, allow_inf_nan=False)
