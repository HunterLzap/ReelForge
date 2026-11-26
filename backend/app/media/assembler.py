import subprocess
from math import ceil

from app.core.config import ROOT, settings


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


FPS = 24
OVERLAP = 8


def clip(folder):
    from struct import unpack

    with (folder / "card.png").open("rb") as f:
        f.seek(16)
        width, height = unpack(">II", f.read(8))
    frames = ceil((duration(folder / "audio.mp3") + 500) * FPS / 1000)
    seconds = frames / FPS
    graph = (
        f"[0:v]zoompan=z='1+0.026*on/{frames}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={width}x{height}:fps={FPS},"
        f"ass=subs.ass[base];color=c=0xebc588:s={width}x6:r={FPS}[line];"
        f"[base][line]overlay=x='-W+W*t/{seconds}':y=0:shortest=1[v]"
    )
    audio = f"loudnorm=I=-16:TP=-1.5:LRA=7,aresample=48000,asetpts=N/SR/TB,adelay=250:all=1,apad,atrim=duration={seconds}"
    ffmpeg(
        folder,
        "-i",
        "card.png",
        "-i",
        "audio.mp3",
        "-filter_complex_threads",
        "2",
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-map",
        "1:a",
        "-af",
        audio,
        "-t",
        f"{seconds:.8f}",
        "-c:v",
        "libx264",
        "-threads",
        str(settings().effective_ffmpeg_threads()),
        "-preset",
        settings().effective_ffmpeg_preset(),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "2",
        "clip.mp4",
    )


def assemble(output, scenes, transition="fade"):
    inputs = []
    filters = []
    frames = []
    for i, scene in enumerate(scenes):
        path = output.parent / "scenes" / scene["id"] / "clip.mp4"
        n = int(
            command(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=nb_frames",
                    "-of",
                    "csv=p=0",
                    path,
                ]
            )
        )
        frames.append(n)
        inputs.extend(["-threads", "2", "-i", path])
        filters.extend(
            [
                f"[{i}:v]settb=1/{FPS},setpts=PTS-STARTPTS[v{i}]",
                f"[{i}:a]aresample=48000:async=1:first_pts=0,apad,atrim=end_sample={n * 48000 // FPS},asetpts=PTS-STARTPTS[a{i}]",
            ]
        )
    video, audio = "v0", "a0"
    total = frames[0]
    for i, n in enumerate(frames[1:], 1):
        if transition == "none":
            filters.append(
                f"[{video}][{audio}][v{i}][a{i}]concat=n=2:v=1:a=1[mixv{i}][mixa{i}]"
            )
            video, audio = f"mixv{i}", f"mixa{i}"
            total += n
            continue
        overlap = min(OVERLAP, n // 2, total // 2)
        filters.extend(
            [
                f"[{video}][v{i}]xfade=transition={transition}:duration={overlap / FPS:.8f}:offset={(total - overlap) / FPS:.8f}[mixv{i}]",
                f"[{audio}][a{i}]acrossfade=ns={overlap * 48000 // FPS}:c1=tri:c2=tri[mixa{i}]",
            ]
        )
        video, audio = f"mixv{i}", f"mixa{i}"
        total += n - overlap
    bgm = sorted(
        p
        for p in (ROOT / "assets/bgm").glob("*")
        if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac"}
    )
    if bgm:
        inputs.extend(["-t", f"{total / FPS:.8f}", "-i", bgm[0]])
        filters.extend(
            [
                f"[{len(scenes)}:a]aresample=48000,aloop=loop=-1:size={total * 48000 // FPS},atrim=end_sample={total * 48000 // FPS},volume=0.09,afade=t=in:d=1,afade=t=out:st={max(0, total / FPS - 1.2)}:d=1.2[bed]",
                f"[{audio}][bed]amix=inputs=2:duration=first:normalize=0[master]",
            ]
        )
        audio = "master"
    ffmpeg(
        output,
        *inputs,
        "-filter_complex_threads",
        "2",
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{video}]",
        "-map",
        f"[{audio}]",
        "-t",
        f"{total / FPS:.8f}",
        "-c:v",
        "libx264",
        "-threads",
        str(settings().effective_ffmpeg_threads()),
        "-preset",
        settings().effective_ffmpeg_preset(),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        "final.tmp.mp4",
    )
    (output / "final.tmp.mp4").replace(output / "final.mp4")


async def export_timeline(doc):
    """Composite all five layers in Remotion, then master audio and mux for streaming."""
    import asyncio
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from app.core.auth import project_dir, resolve_safe_path
    from app.media.limits import slot
    from app.media.proxy import probe
    from app.media.remotion_runner import render_timeline
    from app.media.worker import run_command
    from app.services.storage_manager import guard

    await asyncio.to_thread(guard)
    if not any(doc.tracks.model_dump().values()):
        raise ValueError("时间轴为空")
    output = resolve_safe_path(project_dir(doc.project_id), "output")
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output, prefix="_tmp-") as directory:
        tmp = Path(directory)
        layers = await render_timeline(doc, tmp / "layers.mp4")
        final = tmp / "final.mp4"
        audio = await asyncio.to_thread(
            command,
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                layers,
            ],
        )
        silent_input = (
            [] if audio else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        )
        async with slot("render"):
            await run_command(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    layers,
                    *silent_input,
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0" if audio else "1:a:0",
                    "-shortest",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-af",
                    "alimiter=limit=0.97:level=false:latency=true,apad",
                    "-movflags",
                    "+faststart",
                    final,
                ]
            )
            info = await asyncio.to_thread(probe, final)
            if (info["width"], info["height"]) != (
                doc.resolution.width,
                doc.resolution.height,
            ) or info["duration_ms"] <= 0:
                raise RuntimeError("导出视频规格与时间轴不符")
            final.replace(output / "final.mp4")
    return {
        **info,
        "revision": doc.revision,
        "path": str(output / "final.mp4"),
        "url": f"/workspace/{doc.project_id}/output/final.mp4",
    }
