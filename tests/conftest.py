import os

import pytest

os.environ["MOCK_LLM"] = "true"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "作品 workspace"))
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
    settings.cache_clear()
    assert settings().mock_llm
    yield
    settings.cache_clear()
