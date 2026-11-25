import subprocess
from pathlib import Path

from app.core.config import ROOT


def command(args, cwd=None):
    proc = subprocess.run(
        [str(a) for a in args], cwd=cwd, capture_output=True, check=False
    )
    if proc.returncode:
        raise RuntimeError(
            proc.stderr.decode("utf-8", "replace")[-2500:] or "媒体子进程失败"
        )
    return proc.stdout.decode("utf-8", "replace").strip()


def ffmpeg(folder, *args):
    command(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args],
        folder,
    )


def duration(path):
    return round(
        float(
            command(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "csv=p=0",
                    path,
                ]
            )
        )
        * 1000
    )


def clip(folder):
    # libass resolves this relative subtitle filename inside the scene directory.
    ffmpeg(
        folder,
        "-loop",
        "1",
        "-framerate",
        "24",
        "-i",
        "card.png",
        "-i",
        "audio.mp3",
        "-vf",
        "subtitles=subs.srt:force_style='FontSize=15,Outline=1,MarginV=12'",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-shortest",
        "clip.mp4",
    )


def assemble(output, scenes):
    listing = output / "concat.txt"
    listing.write_text(
        "".join(f"file '../scenes/{s['id']}/clip.mp4'\n" for s in scenes),
        encoding="utf-8",
    )
    bgm = sorted(
        p
        for p in (ROOT / "assets/bgm").glob("*")
        if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac"}
    )
    args = ["-f", "concat", "-safe", "0", "-i", listing.name]
    if bgm:
        args += [
            "-stream_loop",
            "-1",
            "-i",
            str(bgm[0]),
            "-filter_complex",
            "[1:a]volume=0.12[b];[0:a][b]amix=duration=first:normalize=0[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
        ]
    else:
        args += ["-c", "copy"]
    ffmpeg(output, *args, "-movflags", "+faststart", "final.tmp.mp4")
    Path(output / "final.tmp.mp4").replace(output / "final.mp4")
