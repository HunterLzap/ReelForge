import asyncio
import json
import struct

import pytest

from app.agents.director import example
from app.media import assembler, renderer, tts
from app.media.hash_util import content_hash
from app.schemas.storyboard import StoryboardScript


def all_scenes():

    data = example("租房")

    return StoryboardScript.model_validate(data).model_dump()["scenes"]


@pytest.mark.parametrize("index", range(8))
def test_templates(tmp_path, index):

    fmt = list(renderer.SIZES)[index % 3]

    scene = all_scenes()[index]

    renderer.render(
        tmp_path,
        {"target_format": fmt, "theme": "clean_light", "topic": "测试"},
        dict(**scene, order_index=index + 1),
        6,
    )

    png = (tmp_path / "card.png").read_bytes()

    assert struct.unpack(">II", png[16:24]) == renderer.SIZES[fmt]

    assert scene["visual_payload"].get("heading", "") in (
        tmp_path / "card.html"
    ).read_text(encoding="utf-8")


async def test_subtitles_and_clip(tmp_path, monkeypatch):

    folder = tmp_path / "scenes" / "中文 空格"

    folder.mkdir(parents=True)

    p = {
        "target_format": "video_9_16",
        "theme": "editorial_dark",
        "topic": "样片",
        "voice": "mock",
    }

    s = dict(**all_scenes()[0], order_index=1)

    await asyncio.to_thread(renderer.render, folder, p, s, 1)

    assert await tts.narrate(folder, "请核对记录。", p["voice"], p["target_format"]) > 0

    assembler.clip(folder)

    info = json.loads(
        assembler.command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-of",
                "json",
                folder / "clip.mp4",
            ]
        )
    )

    out = tmp_path / "output"
    out.mkdir()
    music = tmp_path / "assets" / "bgm"
    music.mkdir(parents=True)
    assembler.ffmpeg(
        music, "-f", "lavfi", "-i", "sine=frequency=220:duration=1", "bed.wav"
    )
    monkeypatch.setattr(assembler, "ROOT", tmp_path)
    assembler.assemble(out, [{"id": folder.name}])
    assert (
        abs(
            assembler.duration(out / "final.mp4")
            - assembler.duration(folder / "clip.mp4")
        )
        < 3
    )
    assert [x["codec_name"] for x in info["streams"]] == ["h264", "aac"]

    assert "请核对记录" in (folder / "subs.srt").read_text(encoding="utf-8")

    assert content_hash(p, s) != content_hash(p, {**s, "narration": "不同"})


def test_word_timing_and_hash():
    cues = tts.timed_lines(
        "先看。再核。", [(100, 340, "先看"), (1200, 1500, "再核")], 14, 1600
    )
    assert cues == [(350, 590, "先看。"), (1450, 1750, "再核。")]
    scene = {**all_scenes()[0], "order_index": 1}
    p = {"target_format": "video_9_16", "theme": "clean_light", "voice": "test"}
    digest = content_hash(p, scene, 6)
    assert all(
        digest != content_hash({**p, k: v}, scene, 6)
        for k, v in [
            ("brand_label", "频道"),
            ("transition", "slideleft"),
            ("target_format", "cards_3_4"),
        ]
    )
    assert digest != content_hash(p, scene, 7)
