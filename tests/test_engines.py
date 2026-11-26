import json
import os
import shlex
import sys
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import settings
from app.core.llm_client import LLMClient
from app.main import app

SOURCE = {
    "id": "S1",
    "title": "离线演示资料",
    "url": "https://example.org/",
    "snippet": "两幕中文样片。",
    "credibility_note": "验收样本",
}
SCENES = [
    {
        "template_type": "cover",
        "narration": "一起验证中文字幕。",
        "visual_payload": {
            "title": "中文渲染验收",
            "subtitle": "本机协作工作台",
            "tag": "样片",
        },
        "source_ids": ["S1"],
    },
    {
        "template_type": "big_quote",
        "narration": "来源可以逐条核对。",
        "visual_payload": {
            "quote": "记录每一条来源",
            "highlight": "来源",
            "attribution": "编辑手记",
        },
        "source_ids": ["S1"],
    },
]


@pytest.mark.parametrize(
    ("script", "error"),
    [
        (
            "import sys,json; print('说明\\n```json'); print(json.dumps({'prompt':sys.stdin.read()})); print('```')",
            None,
        ),
        ("import sys; sys.exit(3)", "退出码 3"),
        ("import time; time.sleep(5)", "超时"),
    ],
)
async def test_cli(monkeypatch, script, error):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("AGENT_CLI_PRESET", "custom")
    monkeypatch.setenv("AGENT_CLI_CMD", shlex.join([sys.executable, "-c", script]))
    monkeypatch.setenv("AGENT_CLI_TIMEOUT", "0.5")
    settings.cache_clear()
    evidence = ["材料 $(echo '原样传递')"]
    client = LLMClient("agent_cli")
    if error:
        with pytest.raises(RuntimeError, match=error):
            await client.json("任务", evidence, None)
    else:
        assert (
            json.dumps(evidence, ensure_ascii=False)
            in (await client.json("任务", evidence, None))["prompt"]
        )


async def test_engines(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "your_api_key_here")
    settings.cache_clear()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        body = (await client.get("/api/system/engines")).json()
    assert body["mock_llm"] and not body["api_configured"]
    assert body["mcp_config"]["mcpServers"]["reelforge"]["command"] == sys.executable


async def invoke(session, name, **args):
    result = await session.call_tool(name, args)
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


async def test_headless_tools(monkeypatch):
    monkeypatch.setenv("REELFORGE_API_BASE", "http://127.0.0.1:1")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "app.mcp_server"], env=dict(os.environ)
    )
    async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
        await session.initialize()
        names = {tool.name for tool in (await session.list_tools()).tools}
        assert {
            "get_storyboard_schema",
            "create_project",
            "save_research",
            "set_storyboard",
            "update_scene",
            "add_scene",
            "delete_scene",
            "reorder_scenes",
            "render_project",
            "rebuild_project",
            "get_project_status",
            "attach_image",
            "clone_project",
            "cancel_project",
            "list_skills",
            "get_timeline",
            "patch_timeline",
            "undo_timeline",
            "list_review_pins",
            "export_timeline",
            "redo_timeline",
            "create_review_pin",
            "resolve_review_pin",
            "ai_fix_pin",
            "index_local_library",
            "search_media",
            "transcribe_media",
            "auto_rough_cut",
            "get_storage_status",
            "get_system_capabilities",
            "read_skill",
            "get_transcript",
            "edit_transcript_cuts",
            "update_subtitles",
            "search_local_assets",
            "crawl_web_media",
            "capture_webpage_shot",
            "attach_asset",
        } <= names
        pid = (
            await invoke(
                session, "create_project", topic="测试", target_format="cards_3_4"
            )
        )["project_id"]
        await invoke(
            session,
            "save_research",
            project_id=pid,
            outline=["步骤"],
            sources=[SOURCE],
            data_points=[],
            key_facts=[],
        )
        invalid = await session.call_tool(
            "set_storyboard",
            {"project_id": pid, "scenes": [{**SCENES[0], "source_ids": ["missing"]}]},
        )
        assert invalid.isError and "422" in invalid.content[0].text
        await invoke(session, "set_storyboard", project_id=pid, scenes=SCENES)
        result = await invoke(session, "render_project", project_id=pid)
        assert Path(result["path"]).is_file() and result["cache"]["rendered"] == 2
        status = await invoke(session, "get_project_status", project_id=pid)
        sid = status["scenes"][1]["id"]
        await invoke(
            session, "update_scene", project_id=pid, scene_id=sid, narration="已修改"
        )
        assert (await invoke(session, "rebuild_project", project_id=pid))["cache"] == {
            "rendered": 1,
            "reused": 1,
        }


async def test_external_validation_and_project_migration():
    from app.db import repository as repo
    from app.db.database import connection, init
    from app.schemas.project import ProjectCreate

    await init()
    old = await repo.create(ProjectCreate(topic="历史项目"))
    async with connection() as c:
        await c.execute("ALTER TABLE projects DROP COLUMN execution_mode")
    await init()
    await init()
    assert (await repo.project(old["id"]))["execution_mode"] == "api"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        p = (
            await client.post(
                "/api/projects", json={"topic": "验收", "execution_mode": "mcp"}
            )
        ).json()
        path = "/api/projects/" + p["id"]
        assert (await client.post(path + "/run")).status_code == 409
        assert (
            await client.post(
                path + "/research", json={"outline": ["资料"], "sources": [SOURCE]}
            )
        ).is_success
        bad = {**SCENES[0], "visual_payload": {"tag": "缺少必填项"}}
        result = await client.put(path + "/storyboard", json={"scenes": [bad]})
        assert result.status_code == 422
        assert "title" in result.json()["detail"][0]["loc"]
        assert (await client.get(path)).json()["scenes"] == []


async def test_manage_projects(monkeypatch):
    import asyncio

    from app.api.pipeline import tasks
    from app.db.database import init
    from app.pipeline import orchestrator

    await init()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        p = (await c.post("/api/projects", json={"topic": "测试取消"})).json()
        pid = p["id"]
        path = "/api/projects/" + pid

        async def waiting(*args):
            await asyncio.sleep(100)

        with monkeypatch.context() as m:
            m.setattr(orchestrator, "run", waiting)
            await c.post(path + "/run")
            task = tasks[pid]
            assert (await c.delete(path)).status_code == 409
            assert (await c.post(path + "/cancel")).json()["status"] == "CANCELLED"
            assert task.cancelled() and pid not in tasks
            assert (await c.post(path + "/run")).is_success
            await c.post(path + "/cancel")
        await c.post(
            path + "/research", json={"outline": ["摘要"], "sources": [SOURCE]}
        )
        await c.put(path + "/storyboard", json={"scenes": SCENES})
        clone = (
            await c.post(
                path + "/clone",
                json={"topic": "图文副本", "target_format": "cards_3_4"},
            )
        ).json()
        assert clone["status"] == "WAITING_STORYBOARD" and not clone["total_tokens"]
        target = "/api/projects/" + clone["id"]
        assert (
            len(
                (
                    await c.get(
                        "/api/projects?q=副本&target_format=cards_3_4&status=WAITING_STORYBOARD"
                    )
                ).json()
            )
            == 1
        )
        assert (await c.post(target + "/render")).is_success
        kit = (await c.get(target + "/publish-kit")).text
        assert SCENES[0]["narration"] in kit and SOURCE["url"] in kit
        assert (await c.delete(target)).is_success
        assert not orchestrator.folder(clone["id"]).exists()
        assert (await c.get(path)).is_success


async def test_seed_materials(monkeypatch):
    from app.agents.researcher import Researcher
    from app.tools import web_search

    async def forbidden(*args):
        raise AssertionError("离线采编发生外部调用")

    monkeypatch.setattr(web_search, "search", forbidden)
    monkeypatch.setattr(web_search, "material_text", forbidden)
    pack = await Researcher().process(
        "主题", [], "笔记重点\nhttps://example.org/article", True
    )
    assert pack.sources[0].url is None and pack.key_facts[0].claim == "笔记重点"
    assert str(pack.sources[1].url) == "https://example.org/article"
    assert all("用户提供资料" in s.credibility_note for s in pack.sources)

    async def fetched(url):
        return "网页原文如下。"

    monkeypatch.setattr(web_search, "material_text", fetched)
    hits = await web_search.materials("https://example.org/article", False)
    assert hits[0]["snippet"] == "网页原文如下。"


async def test_local_assets_and_media_controls(tmp_path, monkeypatch):
    from PIL import Image

    from app import mcp_server as server
    from app.db.database import init
    from app.media import tts
    from app.media.hash_util import content_hash
    from app.media.renderer import html
    from app.schemas.research import SourceItem
    from app.schemas.storyboard import StoryboardScript

    await init()
    monkeypatch.setenv("REELFORGE_API_BASE", "http://127.0.0.1:1")
    settings.cache_clear()
    path = tmp_path / "配图.png"
    Image.new("RGB", (320, 240), "navy").save(path)
    pid = (await server.create_project("图片验收", "cards_3_4"))["project_id"]
    asset = (await server.attach_image(pid, str(path)))["asset_id"]
    await server.save_research(pid, ["测试"], [SourceItem(**SOURCE)], [], [])
    scene = {
        **SCENES[1],
        "template_type": "image_card",
        "visual_payload": {
            "image_asset": asset,
            "heading": "图片验收",
            "caption": "本机图片",
            "tag": "专题",
            "layout": "framed",
        },
    }
    script = StoryboardScript.model_validate({"scenes": [SCENES[0], scene]})
    await server.set_storyboard(pid, script.scenes)
    r = await server.render_project(pid)
    assert Path(r["path"]).is_file()
    clone = await server.clone_project(pid, "video_9_16")
    assert (settings().workspace_dir / clone["id"] / "assets" / asset).is_file()
    project = {**clone, "id": pid}
    for style in ("arch", "wave", "grid", "minimal"):
        cover = {
            **SCENES[0],
            "order_index": 1,
            "visual_payload": {**SCENES[0]["visual_payload"], "cover_style": style},
        }
        assert "ornament " + style in html(project, cover, 2)
    for style in ("pill_dark", "clean_stroke", "highlight_bar"):
        tts.subtitles(tmp_path, [(200, 1000, "中文字幕")], "video_9_16", style)
        ass = (tmp_path / "subs.ass").read_text("utf-8-sig")
        assert "中文字幕" in ass
        assert ("Dialogue: 0" in ass) == (style != "clean_stroke")
        assert ("H0B9EF5" in ass) == (style == "highlight_bar")
    for key, value in (
        ("speech_rate", "+10%"),
        ("transition", "none"),
        ("subtitle_style", "clean_stroke"),
    ):
        assert content_hash(project, scene) != content_hash(
            {**project, key: value}, scene
        )
    with pytest.raises(ValueError, match="409"):
        await server.cancel_project(pid)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as c:
        assert (
            await c.post(
                f"/api/projects/{pid}/assets", files={"file": ("bad.png", b"fake")}
            )
        ).status_code == 422
        assert len((await c.get(f"/api/projects/{pid}/assets")).json()) == 1
        for transition in ("none", "wipeleft", "slideup", "smoothleft"):
            assert (
                await c.patch(
                    f"/api/projects/{pid}/settings", json={"transition": transition}
                )
            ).is_success


@pytest.mark.parametrize("fmt", ["video_16_9", "video_9_16", "cards_3_4"])
@pytest.mark.parametrize("layout", ["split", "framed", "backdrop"])
async def test_image_card_layout(tmp_path, fmt, layout):
    from io import BytesIO

    from PIL import Image
    from playwright.async_api import async_playwright

    from app.media.assets import store
    from app.media.renderer import SIZES, capture_jobs, launch

    color = (24, 103, 67)
    square = BytesIO()
    Image.new("RGB", (320, 320), color).save(square, format="PNG")
    asset = store("leaf", square.getvalue())
    project = {
        "id": "leaf",
        "topic": "叶脉观察手记",
        "target_format": fmt,
        "theme": "clean_light",
    }
    scene = {
        "order_index": 2,
        "template_type": "image_card",
        "visual_payload": {
            "image_asset": asset["asset_id"],
            "layout": layout,
            "heading": "从中央主脉到叶缘，追踪一片叶子的分支纹理",
            "caption": "把叶片迎着窗光举起，沿着最粗的主脉找到第一处分叉，再用指尖比对两侧支脉的角度，记下它们在叶缘交汇的位置。",
            "tag": "自然观察室 · 秋日野外笔记",
        },
    }
    width, height = SIZES[fmt]
    async with async_playwright() as pw, await launch(pw) as browser:
        # Production capture runs FIT before saving the fitted HTML and PNG.
        await capture_jobs(browser, project, [(tmp_path, scene)], 2)
        with Image.open(tmp_path / "card.png") as card:
            assert card.size == (width, height)
            if layout == "split":
                page = await browser.new_page(viewport={"width": width, "height": height})
                await page.goto((tmp_path / "card.html").as_uri())
                photo = page.locator(".split img")
                assert await photo.evaluate("img => getComputedStyle(img).objectFit") == "cover"
                box = await photo.bounding_box()
                y = int(box["y"] + box["height"] / 2)
                for fraction in (0.02, 0.5, 0.98):
                    x = int(box["x"] + box["width"] * fraction)
                    assert card.getpixel((x, y)) == color
