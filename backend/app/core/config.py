from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    tavily_api_key: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    default_execution_mode: Literal["api", "agent_cli"] = "api"
    agent_cli_preset: Literal["codex", "claude", "custom"] = "codex"
    agent_cli_cmd: str = ""
    agent_cli_timeout: float = Field(180, gt=0)
    reelforge_api_base: str = "http://127.0.0.1:8000"
    mock_llm: bool = False
    max_search_results_per_query: int = Field(4, ge=1)
    max_fact_check_loops: int = Field(1, ge=0)
    max_director_retries: int = Field(2, ge=0)
    default_tts_voice: str = "zh-CN-XiaoxiaoNeural"
    workspace_dir: Path = ROOT / "workspace"
    database_path: Path | None = None
    input_cny_per_million: float = Field(0, ge=0)
    output_cny_per_million: float = Field(0, ge=0)

    @model_validator(mode="after")
    def paths(self):
        self.workspace_dir = (ROOT / self.workspace_dir).resolve()
        self.database_path = (
            (ROOT / self.database_path).resolve()
            if self.database_path
            else self.workspace_dir / "reelforge.db"
        )
        return self


@lru_cache
def settings():
    return Settings()
