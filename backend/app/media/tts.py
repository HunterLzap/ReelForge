import asyncio
import ctypes
import os
import re
import threading
import wave
from pathlib import Path

import edge_tts
import espeakng_loader

from app.core.config import settings
from app.media.assembler import duration, ffmpeg

# eSpeak owns one synthesizer per process.

_speech_lock = threading.Lock()

_callback_type = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p
)


def mock_voice(folder, text, speech_rate="+0%"):

    engine = ctypes.CDLL(espeakng_loader.get_library_path())

    data_dir = os.fsencode(Path(espeakng_loader.get_data_path()).parent)

    pcm = bytearray()

    @_callback_type
    def collect(samples, count, events):

        if samples and count:
            pcm.extend(ctypes.string_at(samples, count * 2))

        return 0

    with _speech_lock:
        rate = engine.espeak_Initialize(2, 0, data_dir, 0x8000)

        if rate <= 0:
            raise RuntimeError("离线配音初始化失败")

        try:
            engine.espeak_SetSynthCallback(collect)

            if engine.espeak_SetVoiceByName(b"cmn") != 0:
                raise RuntimeError("缺少离线普通话语音")

            data = text.encode("utf-8")

            if (
                engine.espeak_Synth(data, len(data) + 1, 0, 1, 0, 1, None, None)
                or not pcm
            ):
                raise RuntimeError("离线配音未生成音频")

        finally:
            engine.espeak_Terminate()

    wav = folder / "voice.wav"

    with wave.open(str(wav), "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "not compressed"))

        output.writeframes(pcm)

    ffmpeg(
        folder,
        "-i",
        wav.name,
        "-af",
        f"atempo={1 + int(speech_rate[:-1]) / 100}",
        "-ar",
        "24000",
        "-ac",
        "1",
        "audio.mp3",
    )

    wav.unlink()


def stamp(ms):

    seconds, ms = divmod(ms, 1000)

    minutes, seconds = divmod(seconds, 60)

    hours, minutes = divmod(minutes, 60)

    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def segment(text, limit):
    return [
        s
        for s in re.findall(
            r"[^，。！？；、,.!?]{1,"
            + str(limit - 1)
            + r"}[，。！？；、,.!?]?|[，。！？；、,.!?]",
            text.replace("\n", " "),
        )
        if s.strip()
    ]


def timed_lines(text, events, limit, length_ms):
    # Attach punctuation omitted by the voice service to the matching word.
    cursor = 0
    spans = []
    for start, end, word in events:
        pos = text.find(word, cursor)
        if pos >= 0:
            cursor = pos + len(word)
            while cursor < len(text) and text[cursor] in "，。！？；、,.!? ":
                cursor += 1
            word = text[pos:cursor]
        spans.append((start, end, word))
    if not spans:
        spans = [(0, length_ms, text)]
    cues = []
    for start, end, words in spans:
        offset = 0
        for part in segment(words, limit):
            a = start + (end - start) * offset // len(words)
            offset += len(part)
            b = start + (end - start) * offset // len(words)
            if (
                cues
                and len(cues[-1][2]) + len(part) <= limit
                and not re.search(r"[，。！？；、,.!?]\s*$", cues[-1][2])
                and a - cues[-1][1] < 450
            ):
                cues[-1] = (cues[-1][0], b, cues[-1][2] + part)
            else:
                cues.append((a, b, part))
    return [
        (a + 250, min(b, length_ms) + 250, part)
        for a, b, part in cues
        if a < min(b, length_ms)
    ]


def ass_time(ms):
    return stamp(ms).replace(",", ".")[1:-1]


def subtitles(folder, cues, fmt, style="pill_dark"):
    import platform
    import unicodedata

    vertical = fmt == "video_9_16"
    width, height = (1080, 1920) if vertical else (1920, 1080)
    size = 57 if vertical else 48
    y = height - (230 if vertical else 82)
    font = {"Windows": "Microsoft YaHei", "Darwin": "PingFang SC"}.get(
        platform.system(), "Noto Sans CJK SC"
    )
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Speech,{font},{size},&H00FFFFFF,&H00FFFFFF,&H70302A24,&H88000000,-1,0,0,0,100,100,0,0,1,1.5,0,5,32,32,{height - y},1",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    srt = []
    for i, (a, b, part) in enumerate(cues, 1):
        times = f"{ass_time(a)},{ass_time(b)},Speech,,0,0,0,,"
        w = (
            round(
                sum(
                    1 if unicodedata.east_asian_width(c) in "WFA" else 0.65
                    for c in part
                )
                * size
            )
            + 48
        )
        h = size + 26
        x = (width - w) // 2
        top = y - h // 2
        r = 14
        path = f"m {r} 0 l {w - r} 0 b {w} 0 {w} 3 {w} {r} l {w} {h - r} b {w} {h} {w - 3} {h} {w - r} {h} l {r} {h} b 0 {h} 0 {h - 3} 0 {h - r} l 0 {r} b 0 0 3 0 {r} 0"
        lines.append(
            "Dialogue: 0,"
            + times
            + "{"
            + f"\\an7\\pos({x},{top})\\bord0\\shad0\\1c&H151515&\\1a&H44&\\p1"
            + "}"
            + path
        )
        effect = ""
        if style == "clean_stroke":
            lines.pop()
            effect = r"\bord3.5\3c&H161616&\3a&H00&"
        elif style == "highlight_bar":
            lines[-1] = lines[-1].replace("H151515", "H0B9EF5").replace("H44", "H00")
            effect = r"\1c&H101010&\bord0"
        safe = part.replace("\\", "＼").replace("{", "｛").replace("}", "｝")
        lines.append(
            "Dialogue: 1,"
            + times
            + "{"
            + effect
            + f"\\pos({width // 2},{y})"
            + "}"
            + safe
        )
        srt.append(f"{i}\n{stamp(a)} --> {stamp(b)}\n{part}\n")
    (folder / "subs.ass").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    (folder / "subs.srt").write_text("\n".join(srt), encoding="utf-8")


async def narrate(
    folder, text, voice, fmt="video_16_9", speech_rate="+0%", subtitle_style="pill_dark"
):
    events = []
    if settings().mock_llm:
        await asyncio.to_thread(mock_voice, folder, text, speech_rate)
    else:
        async with asyncio.timeout(180):
            with (folder / "audio.mp3").open("wb") as out:
                async for item in edge_tts.Communicate(
                    text, voice, rate=speech_rate, boundary="WordBoundary"
                ).stream():
                    if item["type"] == "audio":
                        out.write(item["data"])
                    elif item["type"] in ("WordBoundary", "SentenceBoundary"):
                        events.append(
                            (
                                item["offset"] // 10000,
                                (item["offset"] + item["duration"]) // 10000,
                                item["text"],
                            )
                        )
    ms = await asyncio.to_thread(duration, folder / "audio.mp3")
    subtitles(
        folder,
        timed_lines(text, events, 14 if fmt == "video_9_16" else 20, ms),
        fmt,
        subtitle_style,
    )
    return ms + 500
