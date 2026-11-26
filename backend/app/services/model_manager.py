import asyncio
import ctypes
import ctypes.util
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import psutil
from dotenv import dotenv_values
from fastapi import HTTPException

from app.core.config import ROOT, settings
from app.db import repository as repo
from app.schemas.model_config import ModelConfig

# Each mirror supplies the exact files needed by the runtime, not the whole repo.
CATALOG = {
    "sherpa-onnx-streaming-zipformer-zh": {
        "slot": "asr_speech",
        "provider": "sherpa_onnx",
        "mirrors": ["hf-mirror"],
        "size_mb": 240,
        "repo": "csukuangfj/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23",
        "files": [
            "tokens.txt",
            "encoder-epoch-99-avg-1.int8.onnx",
            "decoder-epoch-99-avg-1.onnx",
            "joiner-epoch-99-avg-1.int8.onnx",
        ],
    },
    "faster-whisper-large-v3": {
        "slot": "asr_speech",
        "provider": "faster_whisper",
        "mirrors": ["hf-mirror", "modelscope"],
        "size_mb": 3100,
        "repo": "Systran/faster-whisper-large-v3",
        "files": [
            "config.json",
            "model.bin",
            "preprocessor_config.json",
            "tokenizer.json",
            "vocabulary.json",
        ],
    },
    "qwen2.5-vl-3b-int4": {
        "slot": "vlm_vision",
        "provider": "ollama",
        "mirrors": ["hf-mirror", "modelscope", "ollama"],
        "size_mb": 2200,
        "ollama": "qwen2.5vl:3b",
        "repo": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
        "files": [
            "model.safetensors",
            "config.json",
            "preprocessor_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
        ],
    },
    "readerlm-v2-1.5b": {
        "slot": "crawler_extract",
        "provider": "ollama",
        "mirrors": ["hf-mirror", "ollama"],
        "size_mb": 950,
        "repo": "roleplaiapp/ReaderLM-v2-Q4_K_M-GGUF",
        "files": ["readerlm-v2-q4_k_m.gguf"],
        "ollama": "milkey/reader-lm-v2:latest",
    },
}
PRESETS = {
    "deepseek": (
        "DeepSeek",
        "https://api.deepseek.com/v1",
        "DEEPSEEK_API_KEY",
        "deepseek-chat",
    ),
    "dashscope": (
        "DashScope / Qwen",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "DASHSCOPE_API_KEY",
        "qwen-plus",
    ),
    "openai": ("OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
    "magpie": ("Magpie", "http://127.0.0.1:3425/v1", "", "default"),
    "gemini": (
        "Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "GEMINI_API_KEY",
        "gemini-2.5-flash",
    ),
    "volcengine": (
        "Volcengine",
        "https://ark.cn-beijing.volces.com/api/v3",
        "ARK_API_KEY",
        "doubao-seed-1-6",
    ),
}


def ram_gb():
    return settings().detected_memory / 1024**3


def policy():
    ram = ram_gb()
    forced = settings().deployment_profile
    recommended = "cloud_2c2g" if forced == "cloud_2c2g" or ram < 4 else "local_mac"
    active = recommended if forced == "auto" else forced
    guarded = active == "cloud_2c2g" or ram < 4
    return {
        "recommended_profile": recommended,
        "active_profile": active,
        "guarded": guarded,
        "guard_explanation": "2C2G OOM 保护：禁止下载或加载超过 300 MB 的本地模型"
        if guarded
        else "可下载本地模型",
    }


def guard_size(size):
    if float(size) > 300 and policy()["guarded"]:
        raise HTTPException(400, policy()["guard_explanation"])


def config_guard(config):
    try:
        size = max(
            config.model_size_mb,
            CATALOG.get(config.model, {}).get("size_mb", 0),
            float(config.extra.get("model_size_mb", 0)),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "模型大小必须是 MB 数值") from exc
    local = config.provider in {"sherpa_onnx", "faster_whisper", "ollama", "local"}
    if local and policy()["guarded"]:
        for entry in CATALOG.values():
            if config.model in {entry.get("ollama"), entry["repo"]}:
                size = max(size, entry["size_mb"])
        if config.provider in {"sherpa_onnx", "faster_whisper"}:
            from app.services.storage_manager import measure

            size = max(size, measure(model_directory(config.model)) / 1_000_000)
    guard_size(size)
    if policy()["guarded"] and local and size <= 0:
        raise HTTPException(400, "2C2G OOM 保护：自定义本地模型需要提供 model_size_mb")


def gpu():
    mps = False
    if sys.platform == "darwin" and (lib := ctypes.util.find_library("Metal")):
        metal = ctypes.CDLL(lib)
        metal.MTLCreateSystemDefaultDevice.restype = ctypes.c_void_p
        mps = bool(metal.MTLCreateSystemDefaultDevice())
    names = []
    if shutil.which("nvidia-smi"):
        try:
            names = (
                subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    timeout=2,
                )
                .decode()
                .splitlines()
            )
        except (OSError, subprocess.SubprocessError):
            pass
    return {"mps": mps, "cuda": bool(names), "devices": names}


async def probe_hardware():
    cfg = settings()
    disk = shutil.disk_usage(cfg.workspace_dir)
    binaries = {
        key: bool(shutil.which(key))
        for key in ("ffmpeg", "ffprobe", "playwright", "ollama", "codex", "claude")
    }
    binaries["playwright"] |= find_spec("playwright") is not None
    async with httpx.AsyncClient(timeout=0.65, trust_env=False) as client:

        async def reachable(url):
            try:
                return (await client.get(url)).status_code < 500
            except httpx.HTTPError:
                return False

        magpie, ollama, lmstudio, graphics = await asyncio.gather(
            reachable("http://127.0.0.1:3425/v1/models"),
            reachable("http://127.0.0.1:11434/api/tags"),
            reachable("http://127.0.0.1:1234/v1/models"),
            asyncio.to_thread(gpu),
        )
    return dict(
        cpu_cores=os.cpu_count() or 1,
        architecture=platform.machine(),
        ram_total_gb=ram_gb(),
        ram_available_gb=round(psutil.virtual_memory().available / 1024**3, 2),
        disk_free_gb=round(disk.free / 1024**3, 2),
        disk_total_gb=round(disk.total / 1024**3, 2),
        gpu=graphics,
        binaries=binaries,
        services={"magpie": magpie, "ollama": ollama, "lm_studio": lmstudio},
        cached_models=[
            marker.parent.name
            for marker in (cfg.workspace_dir / "models").glob("*/.complete")
        ],
        **policy(),
    )


async def slots():
    cfg = settings()
    default = ModelConfig(
        provider="deepseek",
        model=cfg.llm_model,
        base_url=cfg.llm_base_url,
        api_key_env="LLM_API_KEY",
    )
    result = {
        "llm_director": default,
        "crawler_extract": default,
        "vlm_vision": ModelConfig(
            provider="dashscope",
            model="qwen-vl-plus",
            base_url=PRESETS["dashscope"][1],
            api_key_env="DASHSCOPE_API_KEY",
        ),
        "asr_speech": ModelConfig(
            provider="dashscope",
            model="paraformer-realtime-v2",
            base_url=PRESETS["dashscope"][1],
            api_key_env="DASHSCOPE_API_KEY",
        ),
        "tts_voice": ModelConfig(provider="edge_tts", model=cfg.default_tts_voice),
    }
    for row in await repo.rows("SELECT * FROM model_configs"):
        extra = json.loads(row["extra_json"] or "{}")
        result[row["slot"]] = ModelConfig(
            **row, model_size_mb=extra.pop("_declared_size_mb", 0), extra=extra
        )
    return result


async def save(slot, config):
    if config.enabled:
        config_guard(config)
    extra = dict(config.extra)
    if config.model_size_mb:
        extra["_declared_size_mb"] = config.model_size_mb
    await repo.execute(
        """INSERT INTO model_configs(slot,provider,model,base_url,api_key_env,enabled,extra_json)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(slot) DO UPDATE SET provider=excluded.provider,model=excluded.model,
        base_url=excluded.base_url,api_key_env=excluded.api_key_env,enabled=excluded.enabled,
        extra_json=excluded.extra_json,updated_at=CURRENT_TIMESTAMP""",
        slot,
        config.provider,
        config.model,
        config.base_url,
        config.api_key_env,
        config.enabled,
        repo.dump(extra),
    )
    return config


def model_directory(model):
    if Path(model).name != model or model in {".", ".."}:
        raise HTTPException(422, "本地模型必须位于工作区 models 目录")
    from app.core.auth import resolve_safe_path

    return resolve_safe_path(settings().workspace_dir / "models", model)


def credential(config):
    if not config.api_key_env:
        return ""
    return (
        os.environ.get(config.api_key_env)
        or dotenv_values(ROOT / ".env").get(config.api_key_env)
        or ""
    )


def endpoint(config):
    if config.provider == "ollama":
        return (config.base_url or "http://127.0.0.1:11434").removesuffix("/v1") + "/v1"
    return config.base_url or PRESETS.get(config.provider, PRESETS["openai"])[1]


async def connectivity(slot):
    config = (await slots())[slot]
    if not config.enabled:
        return {"ok": False, "message": "槽位已停用"}
    config_guard(config)
    if settings().mock_llm or config.provider == "mock":
        return {"ok": True, "message": "Mock 连接成功"}
    if config.provider == "mcp":
        return {"ok": True, "message": "已配置外部 MCP 转交", "metadata": config.extra}
    if config.provider == "agent_cli":
        from app.core.llm_client import cli_args

        cfg = settings()
        if config.model in {"codex", "claude", "custom"}:
            cfg = cfg.model_copy(update={"agent_cli_preset": config.model})
        args = cli_args(cfg)
        ok = bool(args and shutil.which(args[0]))
        return {"ok": ok, "message": "已找到 CLI" if ok else "找不到配置的 CLI"}
    if config.provider in {"sherpa_onnx", "faster_whisper"}:
        folder = model_directory(config.model)
        ok = find_spec(config.provider) is not None and all(
            (folder / f).is_file()
            for f in CATALOG.get(config.model, {}).get("files", [".complete"])
        )
        return {"ok": ok, "message": "模型可用" if ok else "需要安装引擎并下载模型"}
    if config.provider == "edge_tts":
        from edge_tts import list_voices

        try:
            ok = any(
                v["ShortName"] == config.model
                for v in await asyncio.wait_for(list_voices(), 5)
            )
        except (OSError, TimeoutError):
            ok = False
        return {"ok": ok, "message": "语音可用" if ok else "语音服务不可用"}
    headers = {}
    if config.api_key_env:
        key = credential(config)
        if not key:
            return {"ok": False, "message": "未设置 " + config.api_key_env}
        headers["Authorization"] = "Bearer " + key
    url = (
        endpoint(config) + "/models"
        if config.provider != "ollama"
        else (config.base_url or "http://127.0.0.1:11434").removesuffix("/v1")
        + "/api/tags"
    )
    local = urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"}
    try:
        async with httpx.AsyncClient(timeout=4, trust_env=not local) as client:
            response = await client.get(url, headers=headers)
            return {
                "ok": response.is_success,
                "message": f"HTTP {response.status_code}",
            }
    except httpx.HTTPError:
        return {"ok": False, "message": "无法连接服务"}
