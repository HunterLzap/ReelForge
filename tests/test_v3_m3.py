import asyncio
import base64
import io
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import AsyncOpenAI
from PIL import Image

from app.core.config import settings
from app.db.database import init
from app.main import app
from app.schemas.model_config import ModelConfig
from app.services import asset_indexer, model_manager, model_router, web_sourcing


@pytest.fixture
async def studio(monkeypatch):
    monkeypatch.setenv("LIBRARY_ROOT", "")
    settings.cache_clear()
    await init()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://studio"
    ) as c:
        pid = (
            (await c.post("/api/projects", json={"topic": "Atlas 模型快报"}))
            .raise_for_status()
            .json()["id"]
        )
        yield c, f"/api/projects/{pid}"


def video(path, cuts=True):
    # Three contrasting scenes and full-scale PCM produce real scdet and peak-volume events.
    command = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y"]
    for color in ["black", "white", "black"] if cuts else ["blue"]:
        command += [
            "-f",
            "lavfi",
            "-i",
            f"color={color}:size=320x180:rate=10:duration=0.4",
        ]
    command += ["-f", "lavfi", "-i", "aevalsrc=sin(2*PI*440*t):d=1.2"]
    if cuts:
        command += [
            "-filter_complex",
            "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "3:a",
        ]
    else:
        command += ["-map", "0:v", "-map", "1:a"]
    subprocess.run(
        command + ["-c:v", "libx264", "-c:a", "pcm_s16le", "-shortest", path],
        check=True,
    )


async def test_library_jail(studio, tmp_path, monkeypatch):
    c, _ = studio
    root = settings().library_root
    assert root == settings().workspace_dir / "_library"
    root.mkdir()
    for candidate in ("../", str(tmp_path), str(root / "sub" / "..")):
        assert (
            await c.post("/api/library/index", json={"path": candidate})
        ).status_code in (400, 403)
    (root / "outside").symlink_to(tmp_path, target_is_directory=True)
    for candidate in ("outside", ""):
        assert (
            await c.post("/api/library/index", json={"path": candidate})
        ).status_code in (400, 403)
    (root / "outside").unlink()
    external = tmp_path / "private.png"
    Image.new("RGB", (50, 50)).save(external)
    (root / "portrait.png").symlink_to(external)
    assert (await c.post("/api/library/index", json={})).status_code == 403
    (root / "portrait.png").unlink()
    root.rmdir()
    root.symlink_to(tmp_path, target_is_directory=True)
    assert (await c.post("/api/library/index", json={})).status_code == 403


async def test_scene_cuts_incremental_index_quality_and_search(studio, monkeypatch):
    c, url = studio
    root = settings().library_root / "发布会"
    root.mkdir(parents=True)
    video(root / "Atlas.mov")
    video(root / "midpoint.mov", False)
    Image.new("RGB", (160, 284), "navy").save(root / "产品.png")
    data = (
        (await c.post("/api/library/index", json={"path": "发布会", "aspect": "9:16"}))
        .raise_for_status()
        .json()
    )
    assert data["indexed"] == 3 and not data["errors"]
    entries = {a["filename"]: a for a in data["items"]}
    atlas = entries["Atlas.mov"]
    assert set(atlas["quality_flags"]) == {
        "low_res",
        "aspect_mismatch",
        "clipped_audio",
    }
    assert (atlas["fps"], atlas["width"], atlas["height"]) == (10, 320, 180)
    assert len(atlas["keyframes"]) == 2
    assert len(entries["midpoint.mov"]["keyframes"]) == 1
    assert len(atlas["sha256"]) == 64 and atlas["duration_ms"] == 1200
    assert "发布会" in atlas["tags"] and "Atlas" in atlas["caption"]
    thumb = await c.get(atlas["thumbnail_url"])
    assert Image.open(io.BytesIO(thumb.content)).width > 0
    assert [
        a["filename"]
        for a in (
            await c.get("/api/library/search", params={"q": "发布会", "aspect": "9:16"})
        ).json()
    ] == ["产品.png"]
    monkeypatch.setattr(
        asset_indexer, "analyze", lambda *a: pytest.fail("unchanged file was decoded")
    )
    assert (await c.post("/api/library/index", json={})).json()["indexed"] == 3
    imported = (
        (await c.post(url + "/library/" + atlas["id"] + "/import"))
        .raise_for_status()
        .json()
    )
    assert imported["sha256"] == atlas["sha256"]
    (root / "Atlas.mov").unlink()
    (root / "Atlas.mov").symlink_to(Path(__file__))
    assert (
        await c.post(url + "/library/" + atlas["id"] + "/import")
    ).status_code == 403


@pytest.mark.parametrize(
    "profile,requested,expected",
    [
        ("cloud_2c2g", None, "http"),
        ("cloud_2c2g", True, "playwright"),
        ("local_mac", None, "playwright"),
    ],
)
async def test_sourcing_strategy_and_license(
    studio, monkeypatch, profile, requested, expected
):
    c, url = studio
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", profile)
    settings.cache_clear()
    await model_manager.save(
        "crawler_extract", ModelConfig(provider="mock", model="offline")
    )
    # Force optional Crawl4AI absence. The fallback really launches and closes Chromium.
    monkeypatch.setitem(sys.modules, "crawl4ai", None)
    page = "https://public.example/story"
    raw = b"<html><title>Release notes</title><article><p>Version three adds a local asset library to the studio editor.</p></article></html>"

    @asynccontextmanager
    async def transport(target):
        assert target in (page, "https://public.example/favicon.ico")
        yield (
            httpx.Response(200, headers={"content-type": "text/html"}, content=raw),
            target,
        )

    monkeypatch.setattr(web_sourcing, "public_stream", transport)
    slots = []
    gate = web_sourcing.slot

    @asynccontextmanager
    async def observe(kind):
        async with gate(kind):
            slots.append((kind, settings().effective_browser_concurrency()))
            yield

    monkeypatch.setattr(web_sourcing, "slot", observe)
    r = (
        (
            await c.post(
                url + "/sourcing/fetch",
                json={"url": page, "use_browser": requested, "license": "CC BY 4.0"},
            )
        )
        .raise_for_status()
        .json()
    )
    assert r["strategy"] == expected and r["facts"]
    assert len(slots) == int(expected != "http")
    if profile == "cloud_2c2g" and requested:
        assert slots == [("browser", 1)]
    asset = r["asset"]
    assert (
        asset["source_type"] == "web_fetched"
        and asset["source_url"] == page
        and asset["license"] == "CC BY 4.0"
    )
    assert (
        Image.open(
            io.BytesIO((await c.get("/api/media/" + asset["id"] + "/stream")).content)
        ).format
        == "PNG"
    )


async def test_paste_patch_and_quota(studio, monkeypatch):
    c, url = studio
    draft = (
        (
            await c.post(
                url + "/timeline/patch",
                json={
                    "base_revision": 0,
                    "ops": [
                        {
                            "op": "add_clip",
                            "clip": {
                                "id": "slot",
                                "kind": "placeholder",
                                "end_ms": 900,
                            },
                        }
                    ],
                },
            )
        )
        .raise_for_status()
        .json()
    )
    raw = io.BytesIO()
    Image.new("RGB", (80, 160), "red").save(raw, format="PNG")
    body = {
        "filename": "../../paste.png",
        "image_data_url": "data:image/png;base64,"
        + base64.b64encode(raw.getvalue()).decode(),
        "slot_clip_id": "slot",
        "base_revision": draft["revision"],
    }
    r = (await c.post(url + "/sourcing/paste", json=body)).raise_for_status().json()
    clip = r["timeline"]["tracks"]["video"][0]
    assert (
        clip["kind"] == "image_clip"
        and clip["asset_id"] == r["asset"]["id"]
        and clip["source_state"] == "local_matched"
    )
    assert r["asset"]["filename"] == "paste.png" and r["asset"]["path"].startswith(
        "media/"
    )
    assert (await c.post(url + "/sourcing/paste", json=body)).status_code == 409
    assert (await c.post(url + "/timeline/undo")).json()["tracks"]["video"] == draft[
        "tracks"
    ]["video"]
    assert (
        await c.post(
            url + "/sourcing/paste",
            json={"image_data_url": "data:image/png;base64,YWJj"},
        )
    ).status_code == 422
    monkeypatch.setenv("DISK_LIMIT_GB", "0.0000001")
    settings.cache_clear()
    assert (
        await c.post(
            url + "/sourcing/paste", json={"image_data_url": body["image_data_url"]}
        )
    ).status_code == 507
    assert len((await c.get(url + "/media")).json()) == 1


@pytest.mark.parametrize(
    "provider", ["openai_api", "magpie", "ollama", "agent_cli", "mcp", "mock"]
)
async def test_configured_channels(studio, monkeypatch, provider):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "local_mac")
    settings.cache_clear()
    config = ModelConfig(provider=provider, model="unit", model_size_mb=1)
    await model_manager.save("crawler_extract", config)
    seen = []

    def transport(req):
        seen.append((str(req.url), json.loads(req.content)))
        return httpx.Response(
            200,
            json={
                "id": "c",
                "object": "chat.completion",
                "created": 0,
                "model": "unit",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"answer":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    original = AsyncOpenAI
    monkeypatch.setattr(
        model_router,
        "AsyncOpenAI",
        lambda **kw: original(
            **kw,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
        ),
    )
    cli = AsyncMock(return_value={"answer": "cli"})
    monkeypatch.setattr(model_router, "cli_json", cli)
    result = await model_router.router.complete_json(
        "crawler_extract", "extract", {"data": "sample"}, lambda: {"answer": "mock"}
    )
    if provider == "mcp":
        assert result["provider"] == "mcp" and result["slot"] == "crawler_extract"
    elif provider == "agent_cli":
        assert result["answer"] == "cli" and cli.await_count == 1
    elif provider == "mock":
        assert result["answer"] == "mock"
    else:
        host = {
            "openai_api": "api.openai.com",
            "magpie": "127.0.0.1:3425",
            "ollama": "127.0.0.1:11434",
        }[provider]
        assert result["answer"] == "ok" and host in seen[0][0]
        assert seen[0][1]["model"] == "unit"


@pytest.mark.parametrize(
    "aspect,size",
    [("1:1", (1080, 1080)), ("16:9", (1920, 1080)), ("9:16", (1080, 1920))],
)
async def test_director_four_states_and_news_export(studio, aspect, size):
    c, url = studio
    assert {"ai-news-montage", "screen-tutorial", "motion-editorial"} == {
        s["id"] for s in (await c.get("/api/skills")).json()
    }
    skill = (await c.get("/api/skills/ai-news-montage")).json()
    assert {t["id"] for t in skill["templates"]} == {
        "news_headline",
        "lower_third",
        "ticker_banner",
        "chapter_card",
        "pip_commentary",
    }
    root = settings().library_root
    root.mkdir()
    video(root / "Atlas.mov")
    assert (await c.post("/api/library/index", json={})).json()["indexed"] == 1
    before = (await c.get(url + "/timeline")).json()
    body = {
        "message": "节奏紧凑一些",
        "history": [{"role": "user", "content": "Atlas AI 模型发布"}],
        "aspect_ratio": aspect,
        "skill_id": "ai-news-montage",
    }
    chat = (await c.post(url + "/director/chat", json=body)).raise_for_status().json()
    assert "Atlas" in chat["reply"] and "紧凑" in chat["reply"]
    shots = chat["shots"]
    assert [s["source_state"] for s in shots] == [
        "local_matched",
        "web_fetched",
        "motion_generated",
        "placeholder",
    ]
    assert shots[1]["source_url"] and shots[-1]["placeholder_hint"]
    assert (await c.get(url + "/timeline")).json() == before
    for s in shots:
        s.update(duration_ms=800, narration="简讯")
    body.update(shots=shots, base_revision=chat["base_revision"])
    doc = (await c.post(url + "/director/plan", json=body)).raise_for_status().json()
    assert [s["kind"] for s in doc["tracks"]["video"]] == [
        "video_clip",
        "image_clip",
        "motion_card",
        "placeholder",
    ]
    assert doc["tracks"]["video"][2]["component_id"] == "chapter_card"
    assert {s["component_id"] for s in doc["tracks"]["overlay"]} == {
        "lower_third",
        "ticker_banner",
    }
    assert len(doc["tracks"]["audio"]) == 4 and len(doc["tracks"]["subtitle"]) == 4
    assert (await c.post(url + "/director/plan", json=body)).status_code == 409
    # Add a headline and a PiP referencing the same acquired image as the preview player.
    layers = [
        {
            "op": "add_clip",
            "track": "overlay",
            "clip": {
                "kind": "motion_card",
                "component_id": "pip_commentary",
                "asset_id": shots[1]["asset_id"],
                "props": {"title": "出处"},
                "start_ms": 0,
                "end_ms": 800,
            },
        },
        {
            "op": "add_clip",
            "clip": {
                "kind": "motion_card",
                "component_id": "news_headline",
                "props": {"title": "本期简报"},
                "start_ms": 3200,
                "end_ms": 3600,
            },
        },
    ]
    (
        await c.post(
            url + "/timeline/patch",
            json={"base_revision": doc["revision"], "ops": layers},
        )
    ).raise_for_status()
    exported = (await c.post(url + "/timeline/export")).raise_for_status().json()
    path = Path(exported["path"])
    info = json.loads(
        await asyncio.to_thread(
            subprocess.check_output,
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", path],
        )
    )
    assert {s["codec_name"] for s in info["streams"]} == {"h264", "aac"}
    assert (exported["width"], exported["height"]) == size and abs(
        exported["duration_ms"] - 3600
    ) < 100
    assert not list(path.parent.rglob("*.png")) and not list(path.parent.glob("_tmp*"))
    assert (await c.post(url + "/timeline/undo")).json()["tracks"] == doc["tracks"]
    undo = (await c.post(url + "/timeline/undo")).json()
    assert (
        undo["tracks"] == before["tracks"]
        and undo["skill_id"] == before["skill_id"]
        and undo["aspect_ratio"] == before["aspect_ratio"]
    )
    clean = (
        (
            await c.post(
                url + "/director/chat",
                json={
                    "message": "未知探险记录",
                    "web_enabled": False,
                    "auto_apply": True,
                },
            )
        )
        .raise_for_status()
        .json()
    )
    assert clean["timeline"]["tracks"]["video"][-1]["kind"] == "placeholder"


async def test_concurrent_paste_keeps_one_asset_and_one_revision(studio):
    c, url = studio
    (
        await c.post(
            url + "/timeline/patch",
            json={
                "base_revision": 0,
                "ops": [
                    {
                        "op": "add_clip",
                        "clip": {"id": "poster", "kind": "placeholder", "end_ms": 1800},
                    }
                ],
            },
        )
    ).raise_for_status()
    image = io.BytesIO()
    Image.new("RGB", (96, 80), "blue").save(image, "PNG")
    body = {
        "slot_clip_id": "poster",
        "base_revision": 1,
        "image_data_url": "data:image/png;base64,"
        + base64.b64encode(image.getvalue()).decode(),
    }
    responses = await asyncio.gather(
        *(c.post(url + "/sourcing/paste", json=body) for _ in range(2))
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assets = (await c.get(url + "/media")).json()
    doc = (await c.get(url + "/timeline")).json()
    assert (
        len(assets) == 1
        and doc["revision"] == 2
        and doc["tracks"]["video"][0]["asset_id"] == assets[0]["id"]
    )
    assert (
        len(list((settings().workspace_dir / doc["project_id"] / "media").iterdir()))
        == 1
    )


async def test_streaming_direct_image_and_url_paste(studio, monkeypatch):
    c, url = studio
    raw = io.BytesIO()
    Image.new("RGB", (1024, 1024), "green").save(raw, format="PNG", compress_level=0)
    data = raw.getvalue()
    assert len(data) > 3 * web_sourcing.CHUNK
    public = "https://public.example/diagram"

    @asynccontextmanager
    async def stream(requested):
        assert requested == public
        yield (
            httpx.Response(200, headers={"content-type": "image/png"}, content=data),
            public,
        )

    monkeypatch.setenv("MOCK_LLM", "false")
    settings.cache_clear()
    monkeypatch.setattr(web_sourcing, "public_stream", stream)
    guarded = []
    monkeypatch.setattr(web_sourcing, "guard", guarded.append)
    result = (
        (await c.post(url + "/sourcing/paste", json={"url": public}))
        .raise_for_status()
        .json()
    )
    asset = result["asset"]
    assert (
        asset["source_type"] == "web_fetched"
        and asset["source_url"] == public
        and asset["size_bytes"] == len(data)
    )
    assert sum(guarded) == len(data) and max(guarded) == web_sourcing.CHUNK
    assert (await c.get("/api/media/" + asset["id"] + "/stream")).content == data


async def test_stock_provider_fallback_and_attribution(studio, monkeypatch):
    c, url = studio
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("PEXELS_API_KEY", "offline-pexels-fixture")
    monkeypatch.setenv("PIXABAY_API_KEY", "offline-pixabay-fixture")
    settings.cache_clear()
    hosts = []

    def transport(request):
        hosts.append(request.url.host)
        if request.url.host == "api.pexels.com":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "tags": "示例产品",
                        "pageURL": "https://public.example/item",
                        "videos": {
                            "medium": {"url": "https://public.example/clip.mp4"}
                        },
                    }
                ]
            },
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        web_sourcing.httpx,
        "AsyncClient",
        lambda **opts: client_class(transport=httpx.MockTransport(transport), **opts),
    )
    result = (
        (await c.post(url + "/sourcing/search", json={"q": "产品", "kind": "video"}))
        .raise_for_status()
        .json()
    )
    assert hosts == ["api.pexels.com", "pixabay.com"]
    assert result["results"] == [
        {
            "kind": "video",
            "title": "示例产品",
            "url": "https://public.example/item",
            "media_url": "https://public.example/clip.mp4",
            "license": "Pixabay Content License",
        }
    ]
