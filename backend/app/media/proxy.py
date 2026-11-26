import json
from fractions import Fraction

from app.media.assembler import command
from app.media.limits import slot
from app.media.worker import run_command


def probe(path):
    info = json.loads(
        command(
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
    video = next(
        (
            s
            for s in info["streams"]
            if s["codec_type"] == "video"
            and not s.get("disposition", {}).get("attached_pic")
        ),
        {},
    )
    rate = video.get("avg_frame_rate")
    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": float(Fraction(rate)) if rate and rate != "0/0" else None,
        "duration_ms": round(float(info["format"].get("duration") or 0) * 1000),
    }


async def generate(path, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    try:
        async with slot("render"):
            await run_command(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-threads",
                    "2",
                    "-i",
                    path,
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a?",
                    "-vf",
                    "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "28",
                    "-g",
                    "15",
                    "-pix_fmt",
                    "yuv420p",
                    "-threads",
                    "2",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    tmp,
                ]
            )
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
