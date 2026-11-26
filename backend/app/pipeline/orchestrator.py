import asyncio
import json
import shutil
from time import monotonic
from zipfile import ZipFile

from pydantic import TypeAdapter

from app.agents.director import Director
from app.agents.fact_checker import FactChecker
from app.agents.researcher import Researcher
from app.core.config import settings
from app.core.events import emit
from app.db import repository as repo
from app.media import assembler, worker
from app.media.hash_util import content_hash
from app.schemas.research import FactCheckReport, ResearchPack
from app.schemas.storyboard import SceneItem, StoryboardScript


def folder(pid):
    return settings().workspace_dir / pid


def snapshot(pid, name, value):
    path = folder(pid) / (name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read(pid, name):
    path = folder(pid) / (name + ".json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


async def state(pid, name, message):
    await repo.status(pid, name)
    await emit(pid, name, message)


async def script_snapshot(pid):
    scenes = await repo.scenes(pid)
    snapshot(
        pid,
        "storyboard",
        {
            "scenes": [
                {
                    k: s[k]
                    for k in (
                        "template_type",
                        "narration",
                        "visual_payload",
                        "source_ids",
                    )
                }
                for s in scenes
            ]
        },
    )


async def edit(pid, sid, changes):
    scenes = await repo.scenes(pid)
    row = next((s for s in scenes if s["id"] == sid), None)
    if row is None:
        raise KeyError(sid)
    data = {
        k: row[k]
        for k in ("template_type", "visual_payload", "narration", "source_ids")
    }
    scene = TypeAdapter(SceneItem).validate_python({**data, **changes})
    from app.media.assets import validate_image

    validate_image(pid, scene.visual_payload)
    if (scene.template_type == "cover") != (row["order_index"] == 1):
        raise ValueError("封面必须且只能位于第一幕")
    if not scene.source_ids or set(scene.source_ids) - {
        s["id"] for s in await repo.sources(pid)
    }:
        raise ValueError("分镜来源编号无效")
    await repo.edit_scene(pid, sid, scene)
    await script_snapshot(pid)
    await emit(pid, "EDITOR", f"第 {row['order_index']} 幕已修改")


async def render_all(project, scenes):
    pid = project["id"]
    cards = project["target_format"] == "cards_3_4"
    jobs = []
    for s in scenes:
        path = folder(pid) / "scenes" / s["id"]
        path.mkdir(parents=True, exist_ok=True)
        digest = content_hash(project, s, len(scenes))
        required = ["card.png", "card.html", "meta.json"] + (
            [] if cards else ["clip.mp4", "audio.mp3", "subs.srt", "subs.ass"]
        )
        if digest == s["content_hash"] and all((path / n).is_file() for n in required):
            await repo.rendered(pid, s["id"], digest, s["duration_ms"])
            await emit(pid, "RENDERING", f"复用第 {s['order_index']} 幕缓存")
            continue
        # A partial write can never match a cache entry after interruption.
        await repo.invalidate(pid, s["id"])
        jobs.append((path, s))
    await worker.run("cards", project, jobs, len(scenes))
    for path, s in jobs:
        digest = content_hash(project, s, len(scenes))
        ms = 0
        if not cards:
            ms = await worker.run("encode", path, s["narration"], project)
        (path / "meta.json").write_text(
            repo.dump({"content_hash": digest, "duration_ms": ms}), encoding="utf-8"
        )
        await repo.rendered(pid, s["id"], digest, ms)
        await emit(pid, "RENDERING", f"第 {s['order_index']} 幕已渲染")

    return {"rendered": len(jobs), "reused": len(scenes) - len(jobs)}


def export(project, scenes, sources):
    root = folder(project["id"])
    out = root / "output"
    out.mkdir(exist_ok=True)
    if project["target_format"] == "cards_3_4":
        cards = out / "cards"
        cards.mkdir(exist_ok=True)
        with ZipFile(out / "cards.tmp.zip", "w") as archive:
            for s in scenes:
                dest = cards / f"{s['order_index']:02}.png"
                shutil.copyfile(root / "scenes" / s["id"] / "card.png", dest)
                archive.write(dest, dest.name)
        (out / "cards.tmp.zip").replace(out / "cards.zip")
        keep = {f"{s['order_index']:02}.png" for s in scenes}
        for old in cards.glob("*.png"):
            if old.name not in keep:
                old.unlink()
    else:
        assembler.assemble(out, scenes, project.get("transition", "fade"))
    (out / "sources.md").write_text(
        "# "
        + project["topic"]
        + " · 资料来源\n\n"
        + "\n\n".join(
            f"- [{s['id']}] {s['title']}\n  {s['url'] or '本地笔记'}\n  {s['credibility_note']}"
            for s in sources
        ),
        encoding="utf-8",
    )

    cover = scenes[0]["visual_payload"]
    platform = {
        "video_16_9": "横屏视频",
        "video_9_16": "竖屏短视频",
        "cards_3_4": "图文卡片",
    }[project["target_format"]]
    headings = [
        s["visual_payload"].get("heading") or s["narration"].split("。")[0]
        for s in scenes[1:]
    ]
    if platform == "图文卡片":
        brief = [f"第 {i} 张 · {heading}" for i, heading in enumerate(headings, 2)]
    elif platform == "竖屏短视频":
        brief = [scenes[0]["narration"], *headings[:3]]
    else:
        brief = [cover["subtitle"], *headings]
    lines = [
        f"# {cover['title']}",
        cover["subtitle"],
        f"## {platform}简介",
        *["- " + h for h in (brief or [cover["subtitle"]])],
        "## 建议话题",
        f"#{cover['tag']} #{project['topic']} #{platform}",
        "## 逐幕旁白",
        *[f"{s['order_index']}. {s['narration']}" for s in scenes],
        "## 资料来源",
        *[f"- {s['title']} {s['url'] or ''}" for s in sources],
    ]
    temp = out / "publish_kit.tmp"
    temp.write_text("\n\n".join(lines), encoding="utf-8")
    temp.replace(out / "publish_kit.md")


async def run(pid, action="run"):
    p = await repo.project(pid)
    current = p["status"]
    if action == "approve":
        current = {"WAITING_OUTLINE": "DIRECTING", "WAITING_STORYBOARD": "RENDERING"}[
            current
        ]
    elif action == "rebuild":
        current = "RENDERING"
    elif current == "CANCELLED":
        current = "RENDERING" if await repo.scenes(pid) else "PENDING"
    elif current == "FAILED":
        failures = [e for e in await repo.logs(pid) if e["level"] == "error"]
        current = failures[-1]["stage_name"] if failures else "PENDING"
    if current in ("WAITING_OUTLINE", "WAITING_STORYBOARD", "COMPLETED"):
        return
    try:
        if current == "PENDING":
            current = "RESEARCHING"
        while current in ("RESEARCHING", "FACT_CHECKING"):
            if current == "RESEARCHING":
                await state(pid, current, "正在采编资料")
                prior = read(pid, "fact_check") or {}
                pack = await Researcher(p["execution_mode"]).run(
                    pid,
                    p["topic"],
                    prior.get("follow_up_queries") or prior.get("issues", []),
                    p["seed_materials"],
                    p["seed_only"],
                )
                await repo.save_sources(pid, pack)
                snapshot(pid, "research", pack.model_dump(mode="json"))
                current = "FACT_CHECKING"
            await state(pid, current, "正在交叉核查")
            pack = ResearchPack.model_validate(read(pid, "research"))
            report = await FactChecker(p["execution_mode"]).run(pid, pack)
            snapshot(pid, "fact_check", report.model_dump())
            if report.approved:
                if not p["auto_approve"]:
                    await state(pid, "WAITING_OUTLINE", "等待大纲审批")
                    return
                current = "DIRECTING"
            elif (await repo.project(pid))[
                "fact_check_loops"
            ] < settings().max_fact_check_loops:
                await repo.increment_loops(pid)
                current = "RESEARCHING"
            else:
                raise ValueError("事实核查未通过：" + "；".join(report.issues))
        if current == "DIRECTING":
            await state(pid, current, "正在撰写分镜")
            script = await Director(p["execution_mode"]).run(
                pid,
                p["topic"],
                ResearchPack.model_validate(read(pid, "research")),
                FactCheckReport.model_validate(read(pid, "fact_check")),
                p["target_format"],
            )
            await repo.save_script(pid, StoryboardScript.model_validate(script))
            await script_snapshot(pid)
            if not p["auto_approve"]:
                rows = await repo.scenes(pid)
                jobs = []
                for row in rows:
                    dest = folder(pid) / "previews" / row["id"]
                    dest.mkdir(parents=True, exist_ok=True)
                    jobs.append((dest, row))
                await worker.run("cards", p, jobs, len(rows))
                for dest, row in jobs:
                    (dest / "hash").write_text(content_hash(p, row, len(rows)))
                await state(pid, "WAITING_STORYBOARD", "等待分镜审批")
                return
            current = "RENDERING"
        scenes = await repo.scenes(pid)
        cache = None
        for name in ("RENDERING", "ASSEMBLING"):
            if name == "RENDERING" and current == "ASSEMBLING":
                continue
            current = name
            await state(
                pid, name, "正在渲染分镜" if name == "RENDERING" else "正在导出产物"
            )
            start = monotonic()
            try:
                if name == "RENDERING":
                    cache = await render_all(p, scenes)
                else:
                    await worker.run("export", p, scenes, await repo.sources(pid))
            except (Exception, asyncio.CancelledError) as exc:
                await repo.stage(
                    pid,
                    name,
                    False,
                    (0, 0),
                    round((monotonic() - start) * 1000),
                    "任务已中止"
                    if isinstance(exc, asyncio.CancelledError)
                    else str(exc),
                )
                raise
            await repo.stage(
                pid,
                name,
                True,
                (0, 0),
                round((monotonic() - start) * 1000),
                f"{len(scenes)} 幕",
            )
        await state(pid, "COMPLETED", "产物已就绪")
        return cache
    except Exception as exc:
        await repo.status(pid, "FAILED", str(exc))
        await emit(pid, current, str(exc), "error")
        raise
