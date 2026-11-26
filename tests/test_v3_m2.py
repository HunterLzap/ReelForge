import asyncio
import json
import subprocess
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageChops, ImageStat

from app.core.config import settings
from app.core.events import subscribe
from app.db.database import init
from app.main import app
from app.services import model_manager


@pytest.fixture
async def client():
    await init()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.parametrize(
    ("ram", "profile", "guarded"),
    [
        (16, "auto", False),
        (2, "auto", True),
        (2, "local_mac", True),
        (16, "cloud_2c2g", True),
    ],
)
async def test_hardware_and_model_guards(client, monkeypatch, ram, profile, guarded):
    monkeypatch.setattr(model_manager, "ram_gb", lambda: ram)
    monkeypatch.setattr(settings(), "deployment_profile", profile)
    hw = (await client.post("/api/system/probe")).raise_for_status().json()
    assert hw["ram_total_gb"] == ram and hw["cpu_cores"] >= 1 and hw["disk_free_gb"] > 0
    assert (
        hw["ram_available_gb"] > 0
        and hw["binaries"]["ffmpeg"]
        and "magpie" in hw["services"]
    )
    assert hw["guarded"] == guarded and hw["recommended_profile"] == (
        "cloud_2c2g" if guarded else "local_mac"
    )
    center = (await client.get("/api/models")).json()
    assert set(center["slots"]) == {
        "asr_speech",
        "llm_director",
        "crawler_extract",
        "tts_voice",
        "vlm_vision",
    }
    assert {"deepseek", "openai", "dashscope", "magpie", "gemini", "volcengine"} == {
        p["id"] for p in center["presets"]
    }
    small = "sherpa-onnx-streaming-zipformer-zh"
    config = {
        "provider": "sherpa_onnx",
        "model": small,
        "extra": {"language": "zh"},
        "enabled": True,
    }
    url = "/api/models/asr_speech"
    assert (await client.put(url, json=config)).is_success
    assert (await client.get("/api/models")).json()["slots"]["asr_speech"][
        "extra"
    ] == config["extra"]
    assert (await client.post("/api/models/test", json={"slot": "asr_speech"})).json()[
        "ok"
    ]
    large = "faster-whisper-large-v3"
    save = await client.put(url, json={**config, "model": large, "model_size_mb": 1})
    download = await client.post(
        "/api/models/download", json={"model_id": large, "model_size_mb": 1}
    )
    custom = await client.put(
        url, json={**config, "model": "custom-local", "extra": {"model_size_mb": 301}}
    )
    if guarded:
        for res in [save, download, custom]:
            assert res.status_code in (400, 422) and "2C2G OOM" in res.text
        assert (await client.get("/api/models/downloads")).json() == []
        assert (await client.get("/api/models")).json()["slots"]["asr_speech"][
            "model"
        ] == small
    else:
        assert save.is_success and custom.is_success
        task = download.raise_for_status().json()
        await client.post("/api/models/downloads/" + task["task_id"] + "/cancel")


async def test_download_cancel_resume(client, monkeypatch):
    monkeypatch.setattr(model_manager, "ram_gb", lambda: 16)
    body = {"model": "sherpa-onnx-streaming-zipformer-zh", "mirror": "hf-mirror"}
    task = (await client.post("/api/models/download", json=body)).json()
    await asyncio.sleep(0.12)
    stopped = (
        await client.post("/api/models/downloads/" + task["task_id"] + "/cancel")
    ).json()
    assert (
        stopped["status"] == "cancelled"
        and 0 < stopped["downloaded_bytes"] < stopped["total_bytes"]
    )
    assert (
        settings().workspace_dir / "models" / body["model"] / ".mock.part"
    ).stat().st_size == stopped["downloaded_bytes"]
    retry = (await client.post("/api/models/download", json=body)).json()
    for _ in range(40):
        state = (await client.get("/api/models/downloads")).json()[0]
        if state["status"] == "completed":
            break
        await asyncio.sleep(0.05)
    assert retry["task_id"] == state["task_id"] and state["percentage"] == 100
    assert (
        settings().workspace_dir / "models" / body["model"] / ".mock.complete"
    ).is_file()


@pytest.fixture
async def recording(client, tmp_path):
    project = (
        await client.post(
            "/api/projects", json={"topic": "精剪验收", "skill_id": "screen-tutorial"}
        )
    ).json()
    url = "/api/projects/" + project["id"]
    path = tmp_path / "static-screen.mp4"
    await asyncio.to_thread(
        subprocess.run,
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "smptebars=size=480x270:rate=15",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-af",
            "volume=0:enable='between(t,2,3.2)'",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            path,
        ],
        check=True,
    )
    asset = (
        (
            await client.post(
                "/api/media/upload",
                data={"project_id": project["id"]},
                files={"file": ("screen.mp4", path.read_bytes(), "video/mp4")},
            )
        )
        .raise_for_status()
        .json()
    )
    clip = {
        "id": "screen",
        "asset_id": asset["id"],
        "kind": "video_clip",
        "start_ms": 0,
        "end_ms": 5000,
        "source_in_ms": 500,
        "source_out_ms": 5500,
        "screen_frame": {"padding": 40, "rounded": True},
    }
    await post(
        client,
        url + "/timeline/patch",
        {"base_revision": 0, "ops": [{"op": "add_clip", "clip": clip}]},
    )
    return client, url, asset


async def post(client, url, body=None):
    return (await client.post(url, json=body or {})).raise_for_status().json()


async def test_three_stage_cut_undo_and_word_delete(recording):
    c, url, asset = recording
    result = await post(c, url + "/transcribe", {"asset_id": asset["id"]})
    assert result["engine"] == "mock" and result["silences"]
    assert all(
        0 <= w["start_ms"] < w["end_ms"] <= 5000
        for s in result["segments"]
        for w in s["words"]
    )
    before = (await c.get(url + "/timeline")).json()
    transcript = (await c.get(url + "/transcript")).json()
    assert transcript["transcript"] == result
    preview = await post(c, url + "/rough-cut", {"apply": False, "buffer_ms": 80})
    assert preview["issues"] == transcript["issues"] and preview["saved_ms"] > 600
    assert {"silence", "filler", "retake"} == {i["kind"] for i in preview["issues"]}
    retake = next(i for i in preview["issues"] if i["kind"] == "retake")
    assert "演示" in retake["text"] and "实战" not in retake["text"]
    pause = next(i for i in preview["issues"] if i["kind"] == "silence")
    subset = await post(c, url + "/rough-cut", {"issue_ids": [pause["id"]]})
    assert subset["cut_ranges_ms"] == [[pause["start_ms"] + 80, pause["end_ms"] - 80]]
    assert before == (await c.get(url + "/timeline")).json()
    with subscribe(before["project_id"]) as event:
        edited = (
            await post(
                c,
                url + "/rough-cut",
                {"apply": True, "base_revision": before["revision"]},
            )
        )["timeline"]
        assert event.is_set()
    video = edited["tracks"]["video"]
    assert video[-1]["end_ms"] == 5000 - preview["saved_ms"] and len(video) > 1
    assert all(
        v["end_ms"] - v["start_ms"] == v["source_out_ms"] - v["source_in_ms"]
        for v in video
    )
    assert (
        await c.post(
            url + "/rough-cut",
            json={"apply": True, "base_revision": before["revision"]},
        )
    ).status_code == 409
    after = (await c.get(url + "/transcript")).json()["transcript"]
    assert all(w["deleted"] for w in after["segments"][0]["words"])
    assert "实战" in after["segments"][1]["text"]
    assert [c["text"] for c in edited["tracks"]["subtitle"]] == [
        s["text"] for s in after["segments"] if s["text"]
    ]
    undo = await post(c, url + "/timeline/undo")
    assert (
        undo["tracks"] == before["tracks"]
        and (await c.get(url + "/transcript")).json()["transcript"] == result
    )
    await post(c, url + "/timeline/redo")
    assert (await c.get(url + "/transcript")).json()["transcript"] == after
    await post(c, url + "/timeline/undo")
    word = result["segments"][1]["words"][2]
    cut = await post(
        c, url + "/rough-cut", {"apply": True, "delete_word_ids": [word["id"]]}
    )
    assert cut["saved_ms"] == word["end_ms"] - word["start_ms"]
    clips = cut["timeline"]["tracks"]["video"]
    assert (
        clips[0]["source_out_ms"] == 500 + word["start_ms"]
        and clips[1]["source_in_ms"] == 500 + word["end_ms"]
    )
    assert (await c.get(url + "/transcript")).json()["transcript"]["segments"][1][
        "words"
    ][2]["deleted"]
    assert (
        await c.post(url + "/rough-cut", json={"cut_ranges_ms": [[0, 8000]]})
    ).status_code == 422


async def test_glossary_sync_and_subtitle_formats(recording):
    c, url, _ = recording
    await post(c, url + "/transcribe")
    replaced = await post(
        c,
        url + "/subtitles/batch-replace",
        {"find": "打开时间轴", "replace": "选择 Timeline"},
    )
    assert replaced["replaced_count"] == 1
    captions = replaced["timeline"]["tracks"]["subtitle"]
    assert any("选择 Timeline" in s["text"] for s in captions)
    doc = (await c.get(url + "/transcript")).json()["transcript"]
    assert (
        doc["segments"][2]["text"]
        == captions[2]["text"]
        == "".join(w["text"] for w in doc["segments"][2]["words"] if not w["deleted"])
    )
    assert "选择 Timeline" in doc["hotwords"]
    synced = await post(c, url + "/transcript/sync-subtitles")
    assert [s["text"] for s in synced["tracks"]["subtitle"]] == [
        s["text"] for s in captions
    ]
    for fmt, markers in [
        ("srt", ["1\n00:00:00,000 --> ", "选择 Timeline"]),
        (
            "ass",
            [
                "[Script Info]",
                "[V4+ Styles]",
                "[Events]",
                "Dialogue: 0,0:00:00.00",
                "选择 Timeline",
            ],
        ),
    ]:
        res = await c.get(url + "/subtitles/export?format=" + fmt)
        assert fmt in res.headers["content-disposition"] and all(
            m in res.text for m in markers
        )


def frame(path, time):
    png = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            str(time),
            "-i",
            path,
            "-frames:v",
            "1",
            "-vf",
            "scale=320:180",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ]
    )
    return Image.open(BytesIO(png)).convert("RGB")


@pytest.mark.parametrize(
    "aspect,width,height",
    [("16:9", 1920, 1080), ("9:16", 1080, 1920), ("1:1", 1080, 1080)],
)
async def test_screen_studio_mp4(recording, aspect, width, height):
    c, url, _ = recording
    assert {"screen-tutorial", "motion-editorial"} <= {
        s["id"] for s in (await c.get("/api/skills")).json()
    }
    skill = (await c.get("/api/skills/screen-tutorial")).json()
    assert {t["id"] for t in skill["templates"]} == {
        "window_frame",
        "zoom_focus",
        "spotlight",
        "callout_box",
    }
    box = {"x": 0.55, "y": 0.3, "w": 0.28, "h": 0.2}
    for kind, start in [
        ("zoom_focus", 600),
        ("spotlight", 1800),
        ("callout_box", 3000),
    ]:
        await post(
            c,
            url + "/annotations/zoom",
            {
                "kind": kind,
                "start_ms": start,
                "duration_ms": 1100,
                "target_bbox": box,
                "scale": 2,
                "callout_text": "Export" if kind == "callout_box" else "",
            },
        )
    await post(
        c,
        url + "/timeline/patch",
        {
            "base_revision": 4,
            "ops": [
                {
                    "op": "add_clip",
                    "track": "subtitle",
                    "clip": {
                        "kind": "subtitle",
                        "start_ms": 4100,
                        "end_ms": 5000,
                        "text": "字幕 Export",
                    },
                }
            ],
        },
    )
    await post(
        c,
        url + "/timeline/patch",
        {
            "base_revision": 5,
            "ops": [
                {"op": "set_export_spec", "export": {"aspect_ratio": aspect, "fps": 15}}
            ],
        },
    )
    export = await post(c, url + "/timeline/export")
    path = Path(export["path"])
    streams = json.loads(
        await asyncio.to_thread(
            subprocess.check_output,
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", path],
        )
    )["streams"]
    assert {"h264", "aac"} == {s["codec_name"] for s in streams}
    assert (export["width"], export["height"]) == (width, height)
    assert not list(path.parent.rglob("*.png")) and not list(path.parent.glob("_tmp*"))
    base = frame(path, 0.2)

    def difference(time, rect):
        delta = ImageChops.difference(base, frame(path, time)).crop(rect)
        return sum(ImageStat.Stat(delta).mean) / 3

    # Static source, separate time windows. Each assertion isolates a single layer.
    assert difference(1.2, (30, 20, 275, 145)) > 20
    assert difference(2.4, (10, 10, 120, 80)) > 40
    assert difference(3.6, (178, 56, 261, 87)) > 40
    assert difference(4.6, (110, 145, 210, 171)) > 2


async def test_explicit_cut_preserves_caption_edits_and_other_tracks(recording):
    c, url, _ = recording
    await post(c, url + "/transcribe")
    before = (await c.get(url + "/timeline")).json()
    caption = before["tracks"]["subtitle"][-1]
    await post(
        c,
        url + "/timeline/patch",
        {
            "base_revision": before["revision"],
            "ops": [
                {
                    "op": "update_clip",
                    "track": "subtitle",
                    "clip_id": caption["id"],
                    "patch": {"text": "已校对的片尾"},
                },
                {
                    "op": "add_clip",
                    "track": "annotation",
                    "clip": {"kind": "spotlight", "start_ms": 2200, "end_ms": 3200},
                },
            ],
        },
    )
    result = await post(
        c,
        url + "/rough-cut",
        {"apply": True, "cut_ranges_ms": [[1000, 1600], [1400, 1800]]},
    )
    assert result["saved_ms"] == 800
    tracks = result["timeline"]["tracks"]
    assert (tracks["annotation"][0]["start_ms"], tracks["annotation"][0]["end_ms"]) == (
        1400,
        2400,
    )
    assert tracks["subtitle"][-1]["text"] == "已校对的片尾"
    assert [(v["source_in_ms"], v["source_out_ms"]) for v in tracks["video"]] == [
        (500, 1500),
        (2300, 5500),
    ]


async def test_mirror_resume_checks_actual_sizes(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from app.services.model_downloads import fetch_files

    model = {"repo": "publisher/model", "files": ["weights.bin"]}
    state = {"mirror": "modelscope"}
    data = b"model download"
    (tmp_path / "weights.bin.part").write_bytes(data[:5])
    ranges = []

    def mirror(request):
        header = request.headers["range"]
        ranges.append(header)
        a, b = (0, 0) if header == "bytes=0-0" else (5, len(data) - 1)
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {a}-{b}/{len(data)}"},
            content=data[a : b + 1],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mirror)) as client:
        await fetch_files(client, model, tmp_path, state)
    assert ranges == ["bytes=0-0", "bytes=5-"]
    assert (tmp_path / "weights.bin").read_bytes() == data and state[
        "downloaded_bytes"
    ] == len(data)
    monkeypatch.setattr(model_manager, "ram_gb", lambda: 2)

    def oversize(request):
        assert request.headers["range"] == "bytes=0-0"
        return httpx.Response(
            206, headers={"Content-Range": "bytes 0-0/400000000"}, content=b"A"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(oversize)) as client:
        with pytest.raises(HTTPException, match="2C2G OOM"):
            await fetch_files(client, model, tmp_path, state)
