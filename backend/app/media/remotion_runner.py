"""Render the same player used by previews, staging only referenced project originals."""

import errno
import json
import os
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from app.core.auth import project_dir, resolve_safe_path
from app.core.config import ROOT, settings
from app.db import repository as repo
from app.media.limits import slot
from app.media.worker import run_command
from app.schemas.timeline import TimelineDocument

MOTION = ROOT / "motion"
LOCAL_MEDIA = re.compile(
    r"(?:media/[\w.-]+\.(?:mp4|mov|webm|mp3|wav|m4a|png|jpg|jpeg|webp)|assets/[a-f0-9]{64}\.(?:png|jpg|webp)|scenes/[a-f0-9]{32}/audio\.mp3)"
)


async def staged_props(doc, public):
    values = doc.model_dump()
    pid = doc.project_id
    root = project_dir(pid)
    assets = {row["id"]: row["rel_path"] for row in await repo.media_assets(pid)}
    staged = {}

    def source(src, asset_id=None):
        url = urlsplit(src or "")
        path = unquote(url.path)
        if url.scheme:
            if url.scheme not in ("http", "https") or not url.netloc:
                raise ValueError("不支持的媒体 URL")
            if url.netloc != urlsplit(settings().reelforge_api_base).netloc:
                if f"{url.scheme}://{url.netloc}" not in settings().media_origins:
                    raise ValueError("外部媒体域名未列入 MEDIA_ORIGINS")
                return src
        api_asset = re.fullmatch(r"/api/media/([^/]+)/stream", path)
        if api_asset:
            asset_id = api_asset[1]
        if asset_id:
            if asset_id not in assets:
                raise ValueError("项目中没有该素材：" + asset_id)
            path = assets[asset_id]
        else:
            path = path.removeprefix(f"/workspace/{pid}/")
        if not LOCAL_MEDIA.fullmatch(path):
            raise ValueError("无效的项目媒体路径")
        file = resolve_safe_path(root, path)
        if not file.is_file():
            raise ValueError(f"素材文件不存在：{path}")
        if file not in staged:
            dest = public / (uuid4().hex + file.suffix)
            # Remotion serves regular files. A hard link stages originals without copying bytes.
            try:
                dest.hardlink_to(file)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                shutil.copyfile(file, dest)
            staged[file] = "staged:" + dest.name
        return staged[file]

    for clip in [c for items in values["tracks"].values() for c in items] + (
        [values["bgm"]] if values["bgm"] else []
    ):
        if (
            clip.get("kind") == "placeholder"
            or clip.get("source_state") == "placeholder"
        ):
            continue
        if clip.get("asset_id") or clip.get("src"):
            clip["src"] = source(clip.get("src"), clip.get("asset_id"))
        if (props := clip.get("props")) and props.get("src"):
            props["src"] = source(props["src"])
    return {"timeline": values}


async def render_timeline(
    doc: TimelineDocument, output: Path, *, frame=None, clip_id=None
):
    if clip_id:
        clip = next((c for c in doc.tracks.video if c.id == clip_id), None)
        if clip is None:
            raise ValueError("找不到指定的主轨片段")
        values = doc.model_dump()
        values["tracks"] = {
            "video": [
                dict(clip.model_dump(), start_ms=0, end_ms=clip.end_ms - clip.start_ms)
            ]
        }
        values["bgm"] = None
        doc = TimelineDocument.model_validate(values)
    cfg = settings()
    async with slot("render"), slot("browser"):
        with TemporaryDirectory(
            prefix="_tmp-remotion-", dir=output.parent
        ) as directory:
            temp = Path(directory)
            public = temp / "public"
            public.mkdir()
            props = temp / "props.json"
            props.write_text(
                json.dumps(await staged_props(doc, public), ensure_ascii=False), "utf-8"
            )
            args = [
                "npx",
                "--no-install",
                "remotion",
                "still" if frame is not None else "render",
                "src/Root.tsx",
                "Timeline",
                output.resolve(),
                f"--props={props}",
                f"--public-dir={public}",
                "--log=error",
            ]
            browser = (
                os.getenv("REMOTION_BROWSER_EXECUTABLE")
                or shutil.which("chromium")
                or shutil.which("google-chrome")
            )
            if (
                not browser
                and Path(
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                ).is_file()
            ):
                browser = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if browser:
                args.append(f"--browser-executable={browser}")
            if frame is None:
                args.extend(
                    [
                        f"--concurrency={cfg.effective_browser_concurrency()}",
                        "--codec=h264",
                        f"--x264-preset={cfg.effective_ffmpeg_preset()}",
                    ]
                )
            else:
                args.append(f"--frame={frame}")
            if cfg.is_cloud_2c2g():
                args.extend(
                    [
                        "--offthreadvideo-cache-size-in-bytes=33554432",
                        "--media-cache-size-in-bytes=33554432",
                        "--offthreadvideo-video-threads=1",
                    ]
                )
            await run_command(
                args,
                cwd=MOTION,
                env={
                    **os.environ,
                    "TMPDIR": str(temp),
                    "REELFORGE_ENCODER_THREADS": str(cfg.effective_ffmpeg_threads()),
                },
            )
    return output
