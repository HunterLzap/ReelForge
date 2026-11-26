import asyncio
import base64
import json
import subprocess
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from app.core.auth import resolve_safe_path
from app.core.config import ROOT, settings
from app.core.events import subscribe
from app.db import repository as repo
from app.db.database import init
from app.main import app
from app.media.proxy import probe
from app.schemas.timeline import TimelineDocument
from app.services import skill_registry
from app.services.uploads import CHUNK


@pytest.fixture
async def api():
    await init()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/projects", json={"topic": "动态科普"})
        assert response.status_code == 201
        yield client, response.json()["id"]


def addition(track, id, kind, start, end, **fields):
    return {
        "op": "add_clip",
        "track": track,
        "clip": {"id": id, "kind": kind, "start_ms": start, "end_ms": end, **fields},
    }


async def patch(c, pid, rev, *ops):
    return await c.post(
        f"/api/projects/{pid}/timeline/patch",
        json={"base_revision": rev, "author": "user", "summary": "编辑", "ops": ops},
    )


async def test_migration(api):
    c, pid = api
    await repo.execute(
        "INSERT INTO scenes(id,project_id,order_index,template_type,narration,visual_payload_json,source_ids_json,duration_ms) VALUES(?,?,?,?,?,?,?,?)",
        "a" * 32,
        pid,
        1,
        "hero_stat",
        "配音文本",
        '{"metric":"42"}',
        "[]",
        1260,
    )
    root = settings().workspace_dir / pid
    audio = root / "scenes" / ("a" * 32) / "audio.mp3"
    audio.parent.mkdir(parents=True)
    audio.touch()
    await init()
    await init()
    tables = {
        r["name"]
        for r in await repo.rows("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "projects",
        "scenes",
        "timelines",
        "timeline_revisions",
        "transcripts",
        "media_assets",
        "review_pins",
        "asset_library",
        "model_configs",
    } <= tables
    assert {"skill_id", "timeline_revision", "aspect_ratio"} <= {
        r["name"] for r in await repo.rows("PRAGMA table_info(projects)")
    }
    assert (await repo.rows("PRAGMA integrity_check"))[0]["integrity_check"] == "ok"
    assert not await repo.rows("PRAGMA foreign_key_check")
    doc = (await c.get(f"/api/projects/{pid}/timeline")).json()
    assert doc == json.loads((root / "timeline.json").read_text())
    assert doc["tracks"]["video"][0]["component_id"] == "stat"
    assert doc["tracks"]["video"][0]["end_ms"] == 1260
    assert doc["tracks"]["subtitle"][0]["text"] == "配音文本"
    assert doc["tracks"]["audio"][0]["src"].endswith("audio.mp3")
    await c.get(f"/api/projects/{pid}/timeline")
    assert len(await repo.revisions(pid)) == 1
    assert len(await repo.scenes(pid)) == 1
    assert (await c.delete(f"/api/projects/{pid}")).is_success
    assert not await repo.revisions(pid)


async def test_edits_history_atomicity(api):
    c, pid = api
    path = f"/api/projects/{pid}/timeline"
    doc = (await c.get(path)).json()
    with subscribe(pid) as event:
        result = await patch(
            c,
            pid,
            doc["revision"],
            addition(
                "video",
                "m",
                "motion_card",
                0,
                1000,
                props={"title": "a", "tag": "b"},
                source_in_ms=100,
                source_out_ms=1100,
            ),
        )
        assert result.is_success and event.is_set()
    assert (await repo.logs(pid))[-1]["stage_name"] == "timeline_updated"
    responses = await asyncio.gather(
        *(
            patch(
                c,
                pid,
                1,
                {
                    "op": "update_clip",
                    "clip_id": "m",
                    "patch": {"props": {"title": "c"}},
                },
            )
            for _ in range(2)
        )
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert next(r for r in responses if r.is_error).json()["current_revision"] == 2
    assert (await c.get(path)).json()["tracks"]["video"][0]["props"] == {
        "title": "c",
        "tag": "b",
    }
    bad = await patch(
        c,
        pid,
        2,
        {"op": "delete_clip", "clip_id": "m"},
        {"op": "delete_clip", "clip_id": "missing"},
    )
    assert bad.status_code == 422 and (await c.get(path)).json()["revision"] == 2
    assert (
        await patch(c, pid, 2, {"op": "split_clip", "clip_id": "m", "at_ms": 0})
    ).status_code == 422
    split = (
        await patch(c, pid, 2, {"op": "split_clip", "clip_id": "m", "at_ms": 400})
    ).json()["tracks"]["video"]
    assert [
        (k["start_ms"], k["end_ms"], k["source_in_ms"], k["source_out_ms"])
        for k in split
    ] == [(0, 400, 100, 500), (400, 1000, 500, 1100)]
    second = split[1]["id"]
    reordered = (
        await patch(c, pid, 3, {"op": "reorder", "clip_id": second, "target_index": 0})
    ).json()["tracks"]["video"]
    assert [(k["id"], k["start_ms"], k["end_ms"]) for k in reordered] == [
        (second, 0, 600),
        ("m", 600, 1000),
    ]
    await patch(c, pid, 4, addition("subtitle", "s", "subtitle", 100, 800, text="字幕"))
    cut = (
        await patch(
            c,
            pid,
            5,
            {"op": "ripple_delete", "track": "all", "start_ms": 200, "end_ms": 350},
        )
    ).json()
    for name, expected in [
        ("video", [(0, 200), (200, 450), (450, 850)]),
        ("subtitle", [(100, 200), (200, 650)]),
    ]:
        assert [(k["start_ms"], k["end_ms"]) for k in cut["tracks"][name]] == expected
    assert cut["tracks"]["video"][1]["source_in_ms"] == 850
    result = await patch(
        c,
        pid,
        6,
        {"op": "ripple_delete", "clip_id": second},
        {"op": "delete_clip", "clip_id": "m"},
        {"op": "set_bgm", "bgm": {"asset_id": "music"}},
        {"op": "set_subtitle_style", "style": {"font_size": 48}},
        {"op": "set_export_spec", "spec": {"aspect_ratio": "9:16"}},
    )
    doc = result.json()
    assert doc["resolution"] == {"width": 1080, "height": 1920} and doc["bgm"] == {
        "asset_id": "music"
    }
    assert doc["subtitle_style"] == {"font_size": 48}
    assert len(doc["tracks"]["video"]) == 1
    prev = (await c.post(path + "/undo", json={"base_revision": 7})).json()
    assert prev == dict(cut, revision=8)
    assert (await c.post(path + "/redo")).json() == dict(doc, revision=9)
    assert (await c.post(path + "/undo")).is_success
    assert (await patch(c, pid, 10, {"op": "set_bgm", "bgm": None})).is_success
    assert (await c.post(path + "/redo")).status_code == 409
    assert len((await c.get(path + "/revisions")).json()) == 12
    assert (
        json.loads((settings().workspace_dir / pid / "timeline.json").read_text())
        == (await c.get(path)).json()
    )


async def test_pins(api):
    c, pid = api
    url = f"/api/projects/{pid}/pins"
    fields = {
        "time_ms": 100,
        "bbox": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
        "note": "右移",
        "track": "annotation",
        "clip_id": "a",
    }
    buf = BytesIO()
    Image.new("RGB", (24, 16), "teal").save(buf, "PNG")
    body = dict(
        fields,
        revision=0,
        frame_data_url="data:image/png;base64,"
        + base64.b64encode(buf.getvalue()).decode(),
    )
    pin = (await c.post(url, json=body)).json()
    assert (await c.get(pin["frame_url"])).content == buf.getvalue()
    assert (
        await c.get(f"/workspace/{pid}/" + pin["frame_path"])
    ).content == buf.getvalue()
    assert (await c.get(url)).json() == [pin]
    path = url + "/" + pin["id"]
    updated = (
        await c.patch(
            path, json={"status": "resolved", "note": "已改", "resolved_by_revision": 0}
        )
    ).json()
    assert updated["status"] == "resolved" and updated["resolved_by_revision"] == 0
    assert (await c.delete(path)).is_success
    assert not (settings().workspace_dir / pid / pin["frame_path"]).exists()
    assert (await c.get(pin["frame_url"])).status_code == 404
    assert (
        await c.post(url, json=dict(body, frame_data_url="data:image/png;base64,abc"))
    ).status_code == 422
    fallback = (await c.post(url, json=fields)).json()
    Image.open(BytesIO((await c.get(fallback["frame_url"])).content)).verify()


async def test_skills(api):
    c, _ = api
    skills = (await c.get("/api/skills")).json()
    assert {s["id"] for s in skills} == {s.id for s in skill_registry.list_skills()}
    skill = (await c.get("/api/skills/motion-editorial")).json()
    assert "guide" in skill and {t["id"] for t in skill["templates"]} == {
        "cover",
        "stat",
        "compare",
        "steps",
        "quote",
        "warning",
        "code_card",
        "timeline_card",
        "image_card",
    }
    assert (await c.get("/api/skills/missing")).status_code == 404


async def test_upload_range_auth_storage(api, monkeypatch, tmp_path):
    c, pid = api
    sizes = []
    read = UploadFile.read

    async def observed(self, size=-1):
        sizes.append(size)
        return await read(self, size)

    monkeypatch.setattr(UploadFile, "read", observed)
    payload = b"abcd" * (CHUNK // 2 + 9)
    r = await c.post(
        "/api/media/upload",
        data={"project_id": pid},
        files={"file": ("large.mp4", payload)},
    )
    assert r.status_code == 201 and len(sizes) >= 4 and set(sizes) == {CHUNK}
    asset = r.json()
    url = f"/api/media/{asset['id']}/stream"
    assert (await c.get(f"/api/projects/{pid}/media")).json() == [asset]
    for header, wanted, content_range in [
        ("bytes=1-5", payload[1:6], f"1-5/{len(payload)}"),
        (
            "bytes=-8",
            payload[-8:],
            f"{len(payload) - 8}-{len(payload) - 1}/{len(payload)}",
        ),
    ]:
        part = await c.get(url + "?variant=proxy", headers={"Range": header})
        assert part.status_code == 206 and part.content == wanted
        assert (
            part.headers["content-range"] == "bytes " + content_range
            and part.headers["accept-ranges"] == "bytes"
        )
    assert (await c.get(url, headers={"Range": "bytes=9999999-"})).status_code == 416
    assert (await c.get(url)).content == payload
    monkeypatch.setenv("UPLOAD_MAX_MB", "1")
    monkeypatch.setenv("ACCESS_TOKEN", "test-key")
    monkeypatch.setenv("LIBRARY_ROOT", str(tmp_path / "library"))
    settings.cache_clear()
    assert (await c.get("/api/system/health")).is_success
    assert (await c.get(url)).status_code == 401
    assert (await c.get("/api/skills?token=test-key")).is_success
    assert (await c.get(f"/workspace/{pid}/" + asset["path"])).status_code == 401
    c.headers["Authorization"] = "Bearer test-key"
    assert (
        await c.post(
            "/api/media/upload",
            data={"project_id": pid},
            files={"file": ("large.mp4", payload)},
        )
    ).status_code == 413
    assert (
        await c.post(
            "/api/media/upload",
            data={"project_id": pid},
            files={"file": ("bad.exe", b"bad")},
        )
    ).status_code == 422
    lib = settings().library_root
    lib.mkdir()
    (lib / "link").symlink_to(tmp_path)
    for path in ("../outside", "link/private", str(tmp_path / "outside")):
        with pytest.raises(ValueError):
            resolve_safe_path(lib, path)
    root = settings().workspace_dir / pid
    (root / "cache").mkdir()
    (root / "cache" / "a.tmp").write_bytes(b"cache")
    assert (
        await c.post(
            "/api/system/storage/purge", json={"scope": "temp", "project_id": pid}
        )
    ).json()["freed_bytes"] == 5
    (root / "proxies").mkdir()
    (root / "proxies" / "old.mp4").write_bytes(b"x" * 100)
    r = (await c.get("/api/system/storage")).json()
    assert (
        r["proxies_bytes"] == 100
        and r["status"] == "ok"
        and r["project_breakdown"][pid] >= len(payload) + 100
    )
    assert (
        await c.post(
            "/api/system/storage/purge", json={"scope": "proxies", "project_id": pid}
        )
    ).json()["freed_bytes"] == 100
    assert (root / asset["path"]).is_file() and not list(root.rglob("*.tmp"))
    monkeypatch.setenv("DISK_LIMIT_GB", str(len(payload) / 1024**3))
    settings.cache_clear()
    assert (await c.get("/api/system/storage")).json()["status"] == "critical"
    assert (
        await c.post(
            "/api/media/upload",
            data={"project_id": pid},
            files={"file": ("a.mov", b"123")},
        )
    ).status_code == 507
    assert (await c.post(f"/api/projects/{pid}/export")).status_code == 507


def test_cloud_profile(monkeypatch):
    monkeypatch.setenv("DEPLOY_PROFILE", "cloud_2c2g")
    monkeypatch.setenv("BROWSER_CONCURRENCY", "8")
    monkeypatch.setenv("RENDER_CONCURRENCY", "8")
    settings.cache_clear()
    cfg = settings()
    assert (
        cfg.is_cloud_2c2g()
        and cfg.effective_browser_concurrency()
        == cfg.effective_render_concurrency()
        == 1
    )
    assert (cfg.effective_ffmpeg_threads(), cfg.effective_ffmpeg_preset()) == (
        2,
        "veryfast",
    )


def test_motion_typecheck():
    subprocess.run(
        ["npx", "--no-install", "tsc", "--noEmit"], cwd=ROOT / "motion", check=True
    )


async def test_real_mixed_export(api, tmp_path, monkeypatch):
    c, pid = api
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "cloud_2c2g")
    settings.cache_clear()
    video = tmp_path / "sample.mp4"
    await asyncio.to_thread(
        subprocess.run,
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-c:a",
            "aac",
            video,
        ],
        check=True,
    )
    with video.open("rb") as f:
        r = await c.post(
            "/api/media/upload",
            data={"project_id": pid},
            files={"file": ("source.mp4", f)},
        )
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["width"] == 320 and asset["proxy_path"]
    part = await c.get(
        f"/api/media/{asset['id']}/stream?variant=proxy",
        headers={"Range": "bytes=0-99"},
    )
    assert (
        part.status_code == 206
        and part.content
        == (settings().workspace_dir / pid / asset["proxy_path"]).read_bytes()[:100]
    )
    data = await patch(
        c,
        pid,
        0,
        addition(
            "video",
            "src",
            "video_clip",
            0,
            1000,
            asset_id=asset["id"],
            source_in_ms=500,
            source_out_ms=1500,
            screen_frame={"padding": 32},
        ),
        addition(
            "video",
            "card",
            "motion_card",
            1000,
            2000,
            component_id="cover",
            props={"title": "Mixed motion", "tag": "EDIT"},
        ),
        addition("overlay", "badge", "badge", 400, 1250, text="LIVE"),
        addition("annotation", "focus", "spotlight", 200, 600),
        addition("subtitle", "sub", "subtitle", 300, 1800, text="动态字幕"),
        addition(
            "audio", "voice", "narration", 1000, 2000, asset_id=asset["id"], volume=0.35
        ),
        {
            "op": "set_bgm",
            "bgm": {"asset_id": asset["id"], "volume": 0.12, "fade_in_ms": 100},
        },
    )
    assert data.is_success, data.text
    r = await c.post(f"/api/projects/{pid}/timeline/export")
    assert r.is_success, r.text
    result = r.json()
    final = Path(result["path"])
    metadata = probe(final)
    assert final.is_file() and (metadata["width"], metadata["height"]) == (1920, 1080)
    assert 1960 <= metadata["duration_ms"] <= 2060
    streams = json.loads(
        await asyncio.to_thread(
            subprocess.check_output,
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", final],
        )
    )["streams"]
    assert {s["codec_type"] for s in streams} == {"video", "audio"}

    def sample(time):
        raw = subprocess.check_output(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-ss",
                str(time),
                "-i",
                final,
                "-frames:v",
                "1",
                "-vf",
                "scale=32:18",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ]
        )
        return Image.frombytes("RGB", (32, 18), raw)

    assert len(sample(0.75).getcolors(1024)) > 80
    assert sample(0.75).tobytes() != sample(1.75).tobytes()
    assert not list(final.parent.glob("_tmp*")) and not list(
        final.parent.rglob("*.png")
    )
    assert (await repo.logs(pid))[-1]["stage_name"] == "export_done"

    # Capture the actual motion frame, including the timed subtitle.
    pin = (
        await c.post(
            f"/api/projects/{pid}/pins", json={"time_ms": 1500, "note": "检查标题"}
        )
    ).json()
    with Image.open(BytesIO((await c.get(pin["frame_url"])).content)) as frame:
        assert frame.format == "PNG" and frame.size == (1920, 1080)
        assert frame.convert("RGB").getextrema()[0][1] > 200
    original = final.read_bytes()
    assert (
        await patch(
            c,
            pid,
            1,
            addition("video", "missing", "video_clip", 2000, 2100, asset_id="missing"),
        )
    ).is_success
    failed = await c.post(f"/api/projects/{pid}/export")
    assert failed.status_code == 422
    assert final.read_bytes() == original and not list(final.parent.glob("_tmp*"))
    assert (await repo.logs(pid))[-1]["stage_name"] == "error"


async def test_cloud_slots_and_sse(api, monkeypatch):
    from app.api.stream import stream
    from app.media.limits import slot

    c, pid = api
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "cloud_2c2g")
    settings.cache_clear()

    async def check(kind):
        active = peak = 0

        async def work():
            nonlocal active, peak
            async with slot(kind):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(work(), work(), work())
        assert peak == 1

    await check("render")
    await check("browser")
    await c.get(f"/api/projects/{pid}/timeline")

    class Connected:
        async def is_disconnected(self):
            return False

    events = stream(pid, Connected(), 0)
    try:
        assert "event: timeline_updated" in await anext(events)
    finally:
        await events.aclose()


def test_documented_timeline_input():
    doc = TimelineDocument.model_validate(
        {
            "project_id": "p",
            "format": "video_9_16",
            "tracks": {
                "main_video": [
                    {"id": "a", "kind": "motion_card", "duration_ms": 500},
                    {
                        "id": "b",
                        "kind": "video_clip",
                        "source_in_ms": 1000,
                        "source_out_ms": 3000,
                        "speed": 2,
                    },
                ],
                "subtitle": [
                    {"id": "s", "start_ms": 100, "end_ms": 500, "text": "字幕"}
                ],
            },
        }
    )
    assert [(c.start_ms, c.end_ms) for c in doc.tracks.video] == [(0, 500), (500, 1500)]
    assert doc.resolution.height == 1920
