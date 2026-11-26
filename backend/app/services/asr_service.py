"""Produce timeline-time word spans from trimmed source media."""

import asyncio
import re
import subprocess
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi import HTTPException

from app.core.auth import project_dir, resolve_safe_path
from app.db import repository as repo
from app.media.assembler import command
from app.media.limits import slot
from app.schemas.timeline import Clip
from app.schemas.transcript import TranscriptDocument, TranscriptSegment, WordToken
from app.services.model_manager import credential, endpoint, model_directory
from app.services.model_router import router

FILLERS = {"嗯", "啊", "那个", "就是", "然后", "呃"}


def mock_segments(duration):
    lines = [
        ["嗯", "今天", "我们", "来", "演示", "ReelForge", "审片流程", "呃", "不对"],
        ["今天", "我们", "来", "实战", "ReelForge", "审片流程"],
        ["啊", "那个", "打开", "时间轴", "就是", "定位", "批注"],
        ["然后", "确认", "1080P", "导出", "MP4"],
    ]
    count = sum(map(len, lines))
    gap = min(max(640, duration // 7), max(0, duration - count))
    speech = duration - gap
    i = 0
    result = []
    for n, line in enumerate(lines):
        row = []
        for token in line:
            start = i * speech // count + (gap if n >= 2 else 0)
            i += 1
            end = i * speech // count + (gap if n >= 2 else 0)
            if end > start:
                row.append((token, start, end))
        result.append(row)
    return result


def join_filler_tokens(line):
    # Streaming Chinese models can emit one character per token.
    merged = []
    for text, start, end in line:
        if (
            merged
            and start - merged[-1][2] < 220
            and merged[-1][0] + text.strip(" ，。,.") in FILLERS
        ):
            previous, start, _ = merged.pop()
            text = previous + text
        merged.append((text, start, end))
    return merged


def split_words(words):
    segments = []
    row = []
    for text, a, b in words:
        if row and (
            a - row[-1][2] >= 600
            or row[-1][0].endswith(("。", "！", "？", "."))
            or len(row) >= 16
        ):
            segments.append(row)
            row = []
        row.append((text, a, b))
    if row:
        segments.append(row)
    return segments


def local_segments(config, wav, hotwords):
    folder = model_directory(config.model)
    if not folder.is_dir():
        raise HTTPException(422, "请先在模型中心下载本地 ASR 模型")
    if config.provider == "faster_whisper":
        from faster_whisper import WhisperModel

        model = WhisperModel(
            str(folder), device="cpu", compute_type="int8", local_files_only=True
        )
        sentences, _ = model.transcribe(
            str(wav), word_timestamps=True, hotwords=" ".join(hotwords) or None
        )
        return [
            [
                (w.word, round(w.start * 1000), round(w.end * 1000))
                for w in s.words or []
            ]
            for s in sentences
        ]

    import numpy as np
    import sherpa_onnx

    def network(name):
        files = sorted(folder.glob(name + "*.onnx"))
        if not files:
            raise HTTPException(422, f"本地 ASR 模型缺少 {name} 文件")
        return str(files[0])

    recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=str(folder / "tokens.txt"),
        encoder=network("encoder"),
        decoder=network("decoder"),
        joiner=network("joiner"),
        num_threads=2,
    )
    stream = recognizer.create_stream()
    with wave.open(str(wav)) as audio:
        length = audio.getnframes() / 16000
        while data := audio.readframes(16000):
            stream.accept_waveform(
                16000, np.frombuffer(data, dtype="<i2").astype("float32") / 32768
            )
            while recognizer.is_ready(stream):
                recognizer.decode_stream(stream)
    stream.accept_waveform(16000, np.zeros(8000, dtype="float32"))
    stream.input_finished()
    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)
    stamps = list(recognizer.timestamps(stream))
    return split_words(
        [
            (token.replace("▁", " "), round(a * 1000), round(b * 1000))
            for token, a, b in zip(
                recognizer.tokens(stream), stamps, stamps[1:] + [length]
            )
        ]
    )


def cloud_segments(config, wav, hotwords):
    key = credential(config)
    if config.api_key_env and not key:
        raise HTTPException(422, "缺少 ASR 凭据环境变量 " + config.api_key_env)
    if config.provider == "dashscope":
        from dashscope.audio.asr import Recognition

        result = Recognition(
            model=config.model, format="wav", sample_rate=16000, callback=None
        ).call(str(wav), api_key=key)
        if result.status_code != 200:
            raise HTTPException(502, f"DashScope 转写失败 ({result.status_code})")
        return [
            [
                (
                    w["text"] + (w.get("punctuation") or ""),
                    w["begin_time"],
                    w["end_time"],
                )
                for w in s["words"]
            ]
            for s in result.get_sentence() or []
        ]
    if config.provider not in {"whisper_api", "openai", "openai_api", "magpie"}:
        raise HTTPException(422, "该引擎未提供词级 ASR")
    with wav.open("rb") as audio:
        res = httpx.post(
            endpoint(config) + "/audio/transcriptions",
            headers={"Authorization": "Bearer " + key} if key else {},
            files={"file": ("speech.wav", audio, "audio/wav")},
            data={
                "model": config.model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
                "prompt": " ".join(hotwords),
            },
            timeout=httpx.Timeout(180, connect=5),
        )
        res.raise_for_status()
        return split_words(
            [
                (w["word"], round(w["start"] * 1000), round(w["end"] * 1000))
                for w in res.json()["words"]
            ]
        )


def transcribe_cloud_audio(config, wav, hotwords):
    # Eight minutes of 16 kHz mono PCM fits Whisper's upload limit and bounds
    # the buffer allocated by the synchronous DashScope SDK on a 2 GB host.
    chunk_frames = 8 * 60 * 16000
    with wave.open(str(wav)) as source:
        if source.getnframes() <= chunk_frames:
            return cloud_segments(config, wav, hotwords)
        segments = []
        chunk = wav.with_name("chunk.wav")
        while source.tell() < source.getnframes():
            offset = round(source.tell() * 1000 / source.getframerate())
            with wave.open(str(chunk), "wb") as dest:
                dest.setparams(source.getparams())
                dest.writeframes(source.readframes(chunk_frames))
            for line in cloud_segments(config, chunk, hotwords):
                segments.append(
                    [(text, start + offset, end + offset) for text, start, end in line]
                )
        return segments


def recognize_clip(path, clip, config, mock, hotwords):
    duration = clip.end_ms - clip.start_ms
    source_duration = round(duration * clip.speed)
    audio = command(
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
            path,
        ]
    )
    if not audio:
        if mock:
            return mock_segments(source_duration), []
        raise HTTPException(422, "所选录屏没有音轨")
    with TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        args = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-ss",
            str(clip.source_in_ms / 1000),
            "-i",
            path,
            "-t",
            str(source_duration / 1000),
            "-map",
            "0:a:0",
            "-af",
            "asetpts=PTS-STARTPTS,silencedetect=noise=-35dB:d=0.6",
        ]
        args += (
            ["-f", "null", "-"]
            if mock
            else ["-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)]
        )
        res = subprocess.run(args, capture_output=True, check=True, text=True)
        starts = re.findall(r"silence_start: ([\d.e+-]+)", res.stderr)
        ends = re.findall(r"silence_end: ([\d.e+-]+)", res.stderr)
        pauses = [
            (round(float(a) * 1000), round(float(b) * 1000))
            for a, b in zip(starts, ends)
        ]
        if mock:
            return mock_segments(source_duration), pauses
        if config.provider in {"sherpa_onnx", "faster_whisper"}:
            return local_segments(config, wav, hotwords), pauses
        return transcribe_cloud_audio(config, wav, hotwords), pauses


async def transcribe(timeline, asset_id, hotwords):
    return await router.transcribe(timeline, asset_id, hotwords)


async def transcribe_with(config, timeline, asset_id, hotwords):
    pid = timeline.project_id
    videos = [
        c
        for c in timeline.tracks.video
        if c.kind in {"video", "video_clip"} and getattr(c, "asset_id", None)
    ]
    asset_id = asset_id or (videos[0].asset_id if videos else None)
    clips = [c for c in videos if c.asset_id == asset_id]
    if not asset_id:
        raise HTTPException(422, "请先将录屏素材插入主视频轨，或指定录屏素材")
    asset = next((a for a in await repo.media_assets(pid) if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(404, "项目录屏素材不存在")
    if asset["kind"] != "video" or not asset["duration_ms"]:
        raise HTTPException(422, "请选择具有有效时长的录屏视频")
    if not clips:
        clips = [
            Clip(
                id=asset_id,
                kind="video_clip",
                asset_id=asset_id,
                end_ms=asset["duration_ms"],
            )
        ]
    path = resolve_safe_path(project_dir(pid), asset["rel_path"])
    mock = config.provider == "mock"
    doc = TranscriptDocument(
        asset_id=asset_id,
        engine="mock" if mock else config.model,
        hotwords=hotwords,
        segments=[],
    )
    async with slot("render"):
        for clip in clips:
            try:
                lines, pauses = await asyncio.to_thread(
                    recognize_clip, path, clip, config, mock, hotwords
                )
            except ImportError as exc:
                raise HTTPException(
                    422, f"需要安装 ASR 可选依赖 {config.provider}"
                ) from exc
            except (
                OSError,
                RuntimeError,
                ValueError,
                KeyError,
                subprocess.SubprocessError,
                httpx.HTTPError,
            ) as exc:
                raise HTTPException(
                    502, f"ASR 转写失败 ({type(exc).__name__})"
                ) from exc

            def at(ms, clip=clip):
                return min(clip.end_ms, clip.start_ms + max(0, round(ms / clip.speed)))

            doc.silences.extend((at(a), at(b)) for a, b in pauses if at(b) > at(a))
            for line in lines:
                sid = f"{clip.id}_seg_{len(doc.segments) + 1}"
                words = [
                    WordToken(
                        id=f"{sid}_w{i + 1}",
                        text=text,
                        start_ms=at(a),
                        end_ms=at(b),
                        tag="filler"
                        if text.strip(" ，。！？、,.") in FILLERS
                        else "normal",
                    )
                    for i, (text, a, b) in enumerate(join_filler_tokens(line))
                    if text and at(b) > at(a)
                ]
                if words:
                    doc.segments.append(
                        TranscriptSegment(
                            id=sid,
                            text="".join(w.text for w in words),
                            start_ms=words[0].start_ms,
                            end_ms=words[-1].end_ms,
                            words=words,
                        )
                    )
    return doc
