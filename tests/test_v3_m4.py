import asyncio
import base64
import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

from app.api.stream import stream
from app.core.config import settings
from app.db import repository as repo
from app.db.database import init
from app.main import app

BOX = {"x": 0.13, "y": 0.22, "w": 0.35, "h": 0.18}
SKILLS = ("screen-tutorial", "ai-news-montage", "motion-editorial")


@pytest.fixture
async def client():
    await init()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://studio"
    ) as c:
        yield c


async def post(c, path, body=None):
    return (await c.post(path, json=body)).raise_for_status().json()


async def project(c, **fields):
    p = await post(c, "/api/projects", {"topic": "批注修片验收", **fields})
    return "/api/projects/" + p["id"]


def add(track, kind, **clip):
    return {
        "op": "add_clip",
        "track": track,
        "clip": {"kind": kind, "start_ms": 0, "end_ms": 1200, **clip},
    }


def card():
    return add(
        "video",
        "motion_card",
        id="card",
        component_id="cover",
        props={"title": "原标题"},
    )


async def seed(c, url, *ops):
    return await post(c, url + "/timeline/patch", {"base_revision": 0, "ops": ops})


def pin_fields():
    image = BytesIO()
    Image.new("RGB", (160, 90), "navy").save(image, "PNG")
    return {
        "time_ms": 200,
        "bbox": BOX,
        "note": "高亮此按钮",
        "track": "video",
        "clip_id": "card",
        "frame_data_url": "data:image/png;base64,"
        + base64.b64encode(image.getvalue()).decode(),
    }


async def test_pin_fix_undo_redo_and_branch(client):
    url = await project(client)
    original = await seed(client, url, card())
    pin = await post(client, url + "/pins", pin_fields())
    Image.open(BytesIO((await client.get(pin["frame_url"])).content)).verify()
    fix = url + "/pins/" + pin["id"] + "/ai-fix"
    # Concurrent fixes must never publish two revisions or two resolutions.
    responses = await asyncio.gather(client.post(fix), client.post(fix))
    assert sorted(r.status_code for r in responses) == [200, 409]
    diff = next(r.json() for r in responses if r.is_success)
    assert diff["previous_revision"] == 1
    assert diff["pin"]["status"] == "resolved"
    assert diff["applied_revision"] == diff["pin"]["resolved_by_revision"] == 2
    (mark,) = diff["timeline"]["tracks"]["annotation"]
    assert (mark["target_bbox"], mark["start_ms"], mark["kind"]) == (
        BOX,
        200,
        "spotlight",
    )
    assert (await client.get(url + "/pins")).json() == [diff["pin"]]
    assert (await post(client, url + "/timeline/undo"))["tracks"] == original["tracks"]
    assert (await client.get(url + "/pins")).json()[0]["status"] == "open"
    assert (await post(client, url + "/timeline/redo"))["tracks"] == diff["timeline"][
        "tracks"
    ]
    assert (await client.get(url + "/pins")).json()[0]["status"] == "resolved"
    undo = await post(client, url + "/timeline/undo")
    branch = await post(
        client,
        url + "/chat-edit",
        {"base_revision": undo["revision"], "message": "延长 0.3 秒"},
    )
    assert branch["timeline"]["tracks"]["video"][0]["end_ms"] == 1500
    assert (await client.post(url + "/timeline/redo")).status_code == 409
    assert (await client.get(url + "/pins")).json()[0]["status"] == "open"
    events = [r["stage_name"] for r in await repo.logs(pin["project_id"])]
    assert events.count("pin_resolved") == events.count("pin_updated") == 2


async def test_conversational_edits(client):
    url = await project(client)
    original = await seed(
        client,
        url,
        card(),
        add("subtitle", "subtitle", text="我们先打开设置，核对信息", id="s"),
    )
    body = {
        "base_revision": 1,
        "current_time_ms": 100,
        "selected_clip_id": "s",
        "selected_track": "subtitle",
        "message": "把当前字幕改得更简洁",
    }
    diff = await post(client, url + "/chat-edit", body)
    assert diff["summary"] and diff["ops"][0]["clip_id"] == "s"
    assert diff["timeline"]["tracks"]["subtitle"][0]["text"] == "打开设置"
    assert (await client.post(url + "/chat-edit", json=body)).status_code == 409
    assert (await post(client, url + "/timeline/undo"))["tracks"] == original["tracks"]
    redo = await post(client, url + "/timeline/redo")
    assert redo["history_revision"] == diff["applied_revision"] < redo["revision"]
    assert redo["tracks"] == diff["timeline"]["tracks"]
    next_edit = await post(
        client,
        url + "/chat-edit",
        {
            "base_revision": redo["revision"],
            "history": [{"role": "assistant", "content": diff["summary"]}],
            "message": "把标题改为「放大字幕」",
        },
    )
    assert next_edit["timeline"]["tracks"]["video"][0]["props"]["title"] == "放大字幕"
    last = await post(
        client,
        url + "/chat-edit",
        {
            "base_revision": next_edit["applied_revision"],
            "message": "在 2 秒处加一个放大特写",
        },
    )
    assert last["timeline"]["tracks"]["annotation"][0]["start_ms"] == 2000


@pytest.fixture
def recording(tmp_path):
    path = tmp_path / "screen.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=15",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "1.2",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-c:a",
            "aac",
            path,
        ],
        check=True,
    )
    return path


async def upload(c, pid, path):
    return await c.post(
        "/api/media/upload",
        data={"project_id": pid, "generate_proxy": "false"},
        files={"file": (path.name, path.read_bytes(), "video/mp4")},
    )


async def test_mcp_stdio_closed_loop_and_sse(client, monkeypatch, recording):
    root = recording.parent / "library"
    root.mkdir()
    (root / "screen.mp4").write_bytes(recording.read_bytes())
    monkeypatch.setenv("LIBRARY_ROOT", str(root))
    monkeypatch.setenv("REELFORGE_API_BASE", "http://127.0.0.1:1")
    settings.cache_clear()
    url = await project(client)
    pid = url.split("/")[-1]
    asset = (await upload(client, pid, recording)).raise_for_status().json()
    await seed(
        client,
        url,
        card(),
        add("video", "video_clip", asset_id=asset["id"], start_ms=1200, end_ms=2400),
    )
    cursor = (await client.get(url + "/stream/cursor")).json()["after"]
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "app.mcp_server"], env=dict(os.environ)
    )
    async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
        await session.initialize()

        async def call(name, *, listing=False, **args):
            reply = await session.call_tool(name, args)
            assert not reply.isError, reply.content
            items = [json.loads(item.text) for item in reply.content]
            return items if listing else items[0]

        pin = await call("create_review_pin", project_id=pid, **pin_fields())
        assert await call("list_review_pins", project_id=pid, listing=True) == [pin]
        assert (await client.get(pin["frame_url"])).headers[
            "content-type"
        ] == "image/png"
        base = await call("get_timeline", project_id=pid)
        diff = await call(
            "patch_timeline",
            project_id=pid,
            base_revision=base["revision"],
            review_pin_id=pin["id"],
            summary="高亮按钮",
            ops=[
                add(
                    "annotation",
                    "spotlight",
                    start_ms=pin["time_ms"],
                    target_bbox=pin["bbox"],
                )
            ],
        )
        resolved = await call(
            "resolve_review_pin",
            project_id=pid,
            pin_id=pin["id"],
            resolved_by_revision=diff["revision"],
            summary="已高亮按钮",
        )
        assert (
            resolved["resolved_by_revision"] == diff["revision"]
            and resolved["status"] == "resolved"
        )
        assert (await call("undo_timeline", project_id=pid))["tracks"] == base["tracks"]
        assert (await call("list_review_pins", project_id=pid, listing=True))[0][
            "status"
        ] == "open"
        assert (await call("redo_timeline", project_id=pid))["tracks"] == diff["tracks"]
        another = await call(
            "create_review_pin",
            project_id=pid,
            **dict(pin_fields(), note="把标题改为「外部校对」"),
        )
        fixed = await call("ai_fix_pin", project_id=pid, pin_id=another["id"])
        assert fixed["pin"]["status"] == "resolved"
        assert fixed["timeline"]["tracks"]["video"][0]["props"]["title"] == "外部校对"
        assert (await call("index_local_library"))["indexed"] == 1
        for args in ({}, {"project_id": pid}):
            assert (await call("search_media", query="screen", listing=True, **args))[
                0
            ]["filename"] == "screen.mp4"
        assert (await call("transcribe_media", project_id=pid, asset_id=asset["id"]))[
            "segments"
        ]
        assert "issues" in await call("auto_rough_cut", project_id=pid)
        assert (await call("get_storage_status"))["used_bytes"] > 0

    class Connected:
        async def is_disconnected(self):
            return False

    names = set()
    events = stream(pid, Connected(), cursor)
    try:
        for _ in await repo.logs(pid, cursor):
            chunk = await anext(events)
            row = json.loads(chunk.split("data: ")[1])
            if (
                row["stage_name"] in {"timeline_updated", "pin_resolved"}
                and json.loads(row["message"]).get("author") == "external_mcp"
            ):
                assert f"event: {row['stage_name']}\n" in chunk
                names.add(row["stage_name"])
    finally:
        await events.aclose()
    assert names == {"timeline_updated", "pin_resolved"}


def verify_mp4(result, size):
    path = Path(result["path"])
    info = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                path,
            ]
        )
    )
    (video,) = [s for s in info["streams"] if s["codec_type"] == "video"]
    assert (video["width"], video["height"]) == size
    assert {s["codec_name"] for s in info["streams"]} == {"h264", "aac"}
    assert 1.15 <= float(info["format"]["duration"]) <= 1.55
    assert not list(path.parent.rglob("_tmp*")) and not list(path.parent.rglob("*.png"))


@pytest.mark.parametrize("skill", SKILLS)
@pytest.mark.parametrize(
    "aspect,size",
    [("9:16", (1080, 1920)), ("16:9", (1920, 1080)), ("1:1", (1080, 1080))],
)
async def test_skill_export_matrix(client, recording, skill, aspect, size):
    assert set(SKILLS) == {s["id"] for s in (await client.get("/api/skills")).json()}
    url = await project(client, skill_id=skill, aspect_ratio=aspect)
    if skill == "screen-tutorial":
        asset = (
            (await upload(client, url.split("/")[-1], recording))
            .raise_for_status()
            .json()
        )
        ops = [
            add(
                "video",
                "video_clip",
                asset_id=asset["id"],
                screen_frame={"padding": 32, "rounded": True},
            ),
            add("annotation", "zoom_focus", target_bbox=BOX, scale=1.65),
        ]
    elif skill == "ai-news-montage":
        ops = [
            add(
                "video",
                "motion_card",
                component_id="news_headline",
                props={"title": "模型发布"},
            ),
            add(
                "overlay",
                "motion_card",
                component_id="ticker_banner",
                props={"text": "最新进展"},
            ),
        ]
    else:
        ops = [card()]
    doc = await seed(client, url, *ops)
    assert (doc["skill_id"], doc["aspect_ratio"]) == (skill, aspect)
    verify_mp4(await post(client, url + "/timeline/export"), size)


async def test_cloud_guards_purge_and_render(client, recording, monkeypatch):
    for key, value in {
        "DEPLOYMENT_PROFILE": "cloud_2c2g",
        "REELFORGE_PROBE_RAM_GB": "2",
        "BROWSER_CONCURRENCY": "8",
        "RENDER_CONCURRENCY": "8",
        "ACCESS_TOKEN": "m4-test",
        "DISK_LIMIT_GB": "0.02",
        "LIBRARY_ROOT": str(recording.parent / "library"),
    }.items():
        monkeypatch.setenv(key, value)
    settings.cache_clear()
    cfg = settings()
    assert (
        cfg.effective_browser_concurrency() == cfg.effective_render_concurrency() == 1
    )
    assert (await client.get("/api/system/health")).status_code == 200
    assert (await client.get("/api/skills")).status_code == 401
    assert (await client.get("/api/skills?token=m4-test")).status_code == 200
    client.headers["Authorization"] = "Bearer m4-test"
    assert (await client.get("/api/skills")).status_code == 200
    assert (await post(client, "/api/system/probe"))["ram_total_gb"] == 2
    cfg.library_root.mkdir()
    assert (
        await client.post("/api/library/index", json={"path": "../"})
    ).status_code in (400, 403)
    large = "faster-whisper-large-v3"
    for response in [
        await client.post("/api/models/download", json={"model": large}),
        await client.put(
            "/api/models/asr_speech",
            json={"provider": "faster_whisper", "model": large, "enabled": True},
        ),
    ]:
        assert response.status_code in (400, 422) and "2C2G OOM" in response.text
    url = await project(client)
    pid = url.split("/")[-1]
    await seed(client, url, card())
    cache = cfg.workspace_dir / pid / "cache"
    cache.mkdir()
    with (cache / "preview.tmp").open("wb") as f:
        f.truncate(int(0.91 * cfg.disk_limit_gb * 1024**3))
    assert (await client.get("/api/system/storage")).json()["usage_ratio"] >= 0.9
    assert (await upload(client, pid, recording)).status_code == 507
    assert (await client.post(url + "/export")).status_code == 507
    assert (
        await post(
            client, "/api/system/storage/purge", {"scope": "temp", "project_id": pid}
        )
    )["freed_bytes"] > 0
    asset = (await upload(client, pid, recording)).raise_for_status().json()
    await post(
        client,
        url + "/timeline/patch",
        {
            "base_revision": 1,
            "ops": [
                {"op": "update_clip", "clip_id": "card", "patch": {"end_ms": 600}},
                add(
                    "video",
                    "video_clip",
                    start_ms=600,
                    end_ms=1200,
                    asset_id=asset["id"],
                ),
            ],
        },
    )
    verify_mp4(await post(client, url + "/export"), (1920, 1080))
