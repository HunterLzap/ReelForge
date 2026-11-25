from zipfile import ZipFile

from app.db import repository as repo
from app.db.database import init
from app.media.assembler import duration
from app.pipeline import orchestrator as flow
from app.schemas.project import ProjectCreate
from app.schemas.research import FactCheckReport


async def test_video_end_to_end():
    await init()
    p = await repo.create(ProjectCreate(topic="示范", auto_approve=True))
    await flow.run(p["id"])
    result = await repo.project(p["id"])
    assert result["status"] == "COMPLETED" and result["total_tokens"] == 0
    out = flow.folder(p["id"]) / "output"
    assert duration(out / "final.mp4") > 1000
    assert "https://example.org/" in (out / "sources.md").read_text(encoding="utf-8")


async def test_fact_loop_cards_and_rebuild(monkeypatch):
    await init()
    p = await repo.create(
        ProjectCreate(topic="测试", auto_approve=True, target_format="cards_3_4")
    )
    pid = p["id"]
    replies = iter([False, True])

    async def check(self, pack):
        return FactCheckReport(
            approved=next(replies), summary="核查", issues=["补齐出处"]
        )

    monkeypatch.setattr(flow.FactChecker, "process", check)
    await flow.run(pid)
    assert (await repo.project(pid))["fact_check_loops"] == 1
    scenes = await repo.scenes(pid)
    root = flow.folder(pid)
    paths = [root / "scenes" / s["id"] / "card.png" for s in scenes]
    before = [path.stat().st_mtime_ns for path in paths]
    assert not list(root.rglob("audio.mp3"))
    with ZipFile(root / "output/cards.zip") as z:
        assert z.namelist() == ["01.png", "02.png", "03.png"]
    await flow.edit(pid, scenes[1]["id"], {"narration": "更新文案。"})
    await flow.run(pid, "rebuild")
    assert [path.stat().st_mtime_ns == t for path, t in zip(paths, before)] == [
        True,
        False,
        True,
    ]
    assert len([r for r in await repo.runs(pid) if r["stage_name"] == "Director"]) == 1


async def test_persistent_failed_check(monkeypatch):
    import pytest

    await init()
    pid = (await repo.create(ProjectCreate(topic="模拟失败", auto_approve=True)))["id"]

    async def reject(self, pack):
        return FactCheckReport(approved=False, summary="未通过", issues=["原文缺失"])

    monkeypatch.setattr(flow.FactChecker, "process", reject)
    with pytest.raises(ValueError, match="事实核查"):
        await flow.run(pid)
    assert (await repo.project(pid))["status"] == "FAILED"
