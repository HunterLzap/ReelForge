import os
import subprocess
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
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

    deployment_profile: Literal["auto", "local_mac", "cloud_2c2g"] = Field(
        "auto", validation_alias=AliasChoices("deployment_profile", "deploy_profile")
    )
    access_token: str = ""
    media_origins: list[str] = []
    library_root: Path | None = None
    firecrawl_api_key: str = ""
    jina_api_key: str = ""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    disk_limit_gb: float = Field(40, gt=0)
    upload_max_mb: int = Field(2000, gt=0)
    proxy_profile: Literal["auto", "720p_fast", "none"] = "auto"
    render_concurrency: int = Field(0, ge=0)
    browser_concurrency: int = Field(0, ge=0)

    @cached_property
    def detected_memory(self):
        try:
            return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (AttributeError, OSError, ValueError):
            try:
                with open("/proc/meminfo") as info:
                    return (
                        int(
                            next(
                                line for line in info if line.startswith("MemTotal:")
                            ).split()[1]
                        )
                        * 1024
                    )
            except (OSError, StopIteration, ValueError):
                try:
                    return int(
                        subprocess.check_output(
                            ["sysctl", "-n", "hw.memsize"], timeout=2
                        )
                    )
                except (OSError, ValueError, subprocess.SubprocessError):
                    return 0

    def effective_profile(self):
        if self.deployment_profile != "auto":
            return self.deployment_profile
        low_memory = (
            self.detected_memory < 4 * 1024**3
            if self.detected_memory
            else (os.cpu_count() or 1) <= 2
        )
        return "cloud_2c2g" if low_memory else "local_mac"

    def is_cloud_2c2g(self):
        return self.effective_profile() == "cloud_2c2g"

    def effective_render_concurrency(self):
        return 1 if self.is_cloud_2c2g() else self.render_concurrency or 2

    def effective_browser_concurrency(self):
        return 1 if self.is_cloud_2c2g() else self.browser_concurrency or 2

    def effective_ffmpeg_threads(self):
        return 2 if self.is_cloud_2c2g() else min(os.cpu_count() or 1, 4)

    def effective_ffmpeg_preset(self):
        return "veryfast"

    @field_validator("library_root", mode="before")
    @classmethod
    def empty_library(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def paths(self):
        self.workspace_dir = (ROOT / self.workspace_dir).resolve()
        self.library_root = (
            (ROOT / self.library_root)
            if self.library_root
            else self.workspace_dir / "_library"
        )
        self.database_path = (
            (ROOT / self.database_path).resolve()
            if self.database_path
            else self.workspace_dir / "reelforge.db"
        )
        return self


@lru_cache
def settings():
    return Settings()
