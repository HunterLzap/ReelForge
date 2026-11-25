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


def mock_voice(folder, text):
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
    ffmpeg(folder, "-i", wav.name, "-ar", "24000", "-ac", "1", "audio.mp3")
    wav.unlink()


def stamp(ms):
    seconds, ms = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


async def narrate(folder, text, voice):
    if settings().mock_llm:
        await asyncio.to_thread(mock_voice, folder, text)
    else:
        await edge_tts.Communicate(text, voice).save(str(folder / "audio.mp3"))
    ms = await asyncio.to_thread(duration, folder / "audio.mp3")
    phrases = re.findall(
        r".{1,24}?(?:[，。！？；、,.!?]|$)|.{1,24}", text.replace("\n", " ")
    )
    length = sum(map(len, phrases))
    offset = 0
    cues = []
    for i, phrase in enumerate(phrases, 1):
        start = round(ms * offset / length)
        offset += len(phrase)
        cues.append(
            f"{i}\n{stamp(start)} --> {stamp(round(ms * offset / length))}\n{phrase}\n"
        )
    (folder / "subs.srt").write_text("\n".join(cues), encoding="utf-8")
    return ms
