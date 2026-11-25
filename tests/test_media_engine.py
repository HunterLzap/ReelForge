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
    data["scenes"].extend(
        [
            {
                "template_type": "stat_chart",
                "visual_payload": {
                    "heading": "示意",
                    "unit": "项",
                    "bars": [
                        {"label": s, "value": i, "accent": "#123456"}
                        for i, s in enumerate("甲乙丙")
                    ],
                    "takeaway": "核对记录",
                },
            },
            {
                "template_type": "compare_split",
                "visual_payload": {
                    "heading": "对照",
                    "left_title": "前",
                    "right_title": "后",
                    "left_points": ["核查"],
                    "right_points": ["留存"],
                },
            },
            {
                "template_type": "timeline",
                "visual_payload": {
                    "heading": "步骤",
                    "steps": [
                        {"step_label": str(i), "title": "核查", "desc": "留存记录"}
                        for i in range(3)
                    ],
                },
            },
        ]
    )
    for s in data["scenes"]:
        s.setdefault("source_ids", ["S1"])
        s.setdefault("narration", "核对记录。")
    return StoryboardScript.model_validate(data).model_dump()["scenes"]


@pytest.mark.parametrize("index", range(6))
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


async def test_subtitles_and_clip(tmp_path):
    folder = tmp_path / "中文 空格"
    folder.mkdir()
    p = {
        "target_format": "video_9_16",
        "theme": "editorial_dark",
        "topic": "样片",
        "voice": "mock",
    }
    s = dict(**all_scenes()[0], order_index=1)
    await asyncio.to_thread(renderer.render, folder, p, s, 1)
    assert await tts.narrate(folder, "请核对记录。", p["voice"]) > 0
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
    assert [x["codec_name"] for x in info["streams"]] == ["h264", "aac"]
    assert "请核对记录" in (folder / "subs.srt").read_text(encoding="utf-8")
    assert content_hash(p, s) != content_hash(p, {**s, "narration": "不同"})
