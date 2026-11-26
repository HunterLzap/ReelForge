import asyncio
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from PIL import Image, ImageFilter, ImageStat

from app.core.auth import UnsafePath, resolve_safe_path
from app.core.config import settings
from app.db import repository as repo
from app.media import proxy
from app.media.limits import slot
from app.schemas.asset import EXTENSIONS
from app.schemas.library import LibraryItem
from app.services.model_router import router


def library_path(candidate=""):
    base = settings().library_root
    try:
        if base.is_symlink() or ".." in base.parts:
            raise UnsafePath("片库根目录无效")
        return resolve_safe_path(base, candidate)
    except (UnsafePath, RuntimeError) as exc:
        raise HTTPException(403, "路径超出本地片库") from exc


def cache_path(aid, name=""):
    root = settings().workspace_dir
    return resolve_safe_path(root, Path("_library_cache") / aid / name)


def discover(directory):
    files = []
    for parent, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs + names:
            path = library_path(Path(parent) / name)
            kind = next(
                (
                    kind
                    for kind, extensions in EXTENSIONS.items()
                    if path.suffix.lower()[1:] in extensions
                ),
                None,
            )
            if kind and path.is_file():
                files.append((path, kind))
    return sorted(files)


def mismatch(width, height, aspect):
    if not width or not height:
        return False
    ratio = width / height
    if not aspect:
        return ratio > 2.4 or ratio < 1 / 2.4
    x, y = map(int, aspect.split(":"))
    return max(ratio * y / x, x / y / ratio) > 1.2


def analyze(path, kind, aid):
    with path.open("rb") as src:
        digest = hashlib.file_digest(src, "sha256").hexdigest()
    cache = cache_path(aid)
    cache.mkdir(parents=True, exist_ok=True)
    flags, frames = [], []
    with TemporaryDirectory(dir=cache) as tmp:
        directory = Path(tmp)
        if kind == "image":
            with Image.open(path) as im:
                info = {
                    "width": im.width,
                    "height": im.height,
                    "fps": None,
                    "duration_ms": None,
                }
                im.thumbnail((640, 640))
                im.convert("RGB").save(directory / "01.jpg")
        else:
            info = proxy.probe(path)
            if kind == "video":
                # sc_pass emits just the scene changes. A single shot needs a midpoint still.
                common = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y"]
                scale = "scale=480:480:force_original_aspect_ratio=decrease"
                subprocess.run(
                    common
                    + [
                        "-i",
                        path,
                        "-vf",
                        "scdet=threshold=10:sc_pass=1," + scale,
                        "-fps_mode",
                        "vfr",
                        "-frames:v",
                        "4",
                        directory / "%02d.jpg",
                    ],
                    capture_output=True,
                    check=False,
                )
                if not list(directory.glob("*.jpg")):
                    subprocess.run(
                        common
                        + [
                            "-ss",
                            str((info["duration_ms"] or 0) / 2000),
                            "-i",
                            path,
                            "-vf",
                            scale,
                            "-frames:v",
                            "1",
                            directory / "01.jpg",
                        ],
                        capture_output=True,
                        check=True,
                    )
                if not list(directory.glob("*.jpg")):
                    subprocess.run(
                        common
                        + [
                            "-i",
                            path,
                            "-vf",
                            scale,
                            "-frames:v",
                            "1",
                            directory / "01.jpg",
                        ],
                        capture_output=True,
                        check=True,
                    )
            volume = subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-nostats",
                    "-i",
                    path,
                    "-vn",
                    "-af",
                    "volumedetect",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            peak = re.search(r"max_volume: ([-\d.]+) dB", volume.stderr)
            if peak and float(peak[1]) >= -0.3:
                flags.append("clipped_audio")
        if info["width"] and min(info["width"], info["height"]) < 720:
            flags.append("low_res")
        thumbnails = sorted(directory.glob("*.jpg"))
        if thumbnails:
            with Image.open(thumbnails[0]) as image:
                gray = image.convert("L")
                if min(gray.size) > 4 and ImageStat.Stat(gray).stddev[0] > 15:
                    # Exclude the convolution border and flat title cards.
                    edges = gray.filter(
                        ImageFilter.Kernel(
                            (3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128
                        )
                    )
                    if (
                        ImageStat.Stat(
                            edges.crop((1, 1, gray.width - 1, gray.height - 1))
                        ).var[0]
                        < 12
                    ):
                        flags.append("blurry")
        for file in thumbnails:
            name = digest[:16] + "-" + file.name
            file.replace(cache_path(aid, name))
            frames.append(name)
    return digest, info, flags, frames


def item(row, aspect=None):
    frames = json.loads(row["keyframes_json"] or "[]")
    flags = json.loads(row["quality_flags_json"] or "[]")
    if aspect:
        flags = [f for f in flags if f != "aspect_mismatch"]
        if mismatch(row["width"], row["height"], aspect):
            flags.append("aspect_mismatch")
    return LibraryItem.model_validate(
        {
            **row,
            "filename": Path(row["rel_path"]).name,
            "quality_flags": flags,
            "tags": json.loads(row["tags_json"] or "[]"),
            "keyframes": frames,
            "thumbnail_url": f"/api/library/items/{row['id']}/thumb"
            if frames
            else None,
        }
    )


async def index(request):
    root = library_path()
    directory = library_path(request.path)
    if directory == root:
        root.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise HTTPException(400, "片库目录不存在")
    files = await asyncio.to_thread(discover, directory)
    existing = {
        r["rel_path"]: r
        for r in await repo.rows(
            "SELECT * FROM asset_library WHERE root_path=?", str(root)
        )
    }
    items, errors = [], []
    for path, kind in files:
        rel = str(path.relative_to(root))
        row = existing.get(rel)
        stat = path.stat()
        aid = row["id"] if row else uuid5(NAMESPACE_URL, str(path)).hex
        if (
            row
            and (row["mtime_ns"], row["size_bytes"]) == (stat.st_mtime_ns, stat.st_size)
            and all(
                cache_path(aid, name).is_file()
                for name in json.loads(row["keyframes_json"] or "[]")
            )
        ):
            entry = item(row, request.aspect)
            if request.aspect and entry.quality_flags != json.loads(
                row["quality_flags_json"]
            ):
                await repo.execute(
                    "UPDATE asset_library SET quality_flags_json=? WHERE id=?",
                    repo.dump(entry.quality_flags),
                    aid,
                )
            items.append(entry)
            continue
        try:
            async with slot("render"):
                digest, info, flags, frames = await asyncio.to_thread(
                    analyze, library_path(path), kind, aid
                )
            description = await router.caption(
                path,
                {**info, "kind": kind},
                cache_path(aid, frames[0]) if frames else None,
            )
        except (
            ValueError,
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
            HTTPException,
        ) as exc:
            errors.append({"path": rel, "message": str(exc)})
            continue
        if mismatch(info["width"], info["height"], request.aspect):
            flags.append("aspect_mismatch")
        values = dict(
            id=aid,
            root_path=str(root),
            rel_path=rel,
            kind=kind,
            sha256=digest,
            **info,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            caption=description["caption"],
            tags_json=repo.dump(description["tags"]),
            quality_flags_json=repo.dump(flags),
            keyframes_json=repo.dump(frames),
        )
        columns = list(values)
        await repo.execute(
            "INSERT INTO asset_library ("
            + ",".join(columns)
            + ") VALUES ("
            + ",".join("?" for _ in columns)
            + ") ON CONFLICT(root_path,rel_path) DO UPDATE SET indexed_at=CURRENT_TIMESTAMP,"
            + ",".join(
                f"{key}=excluded.{key}"
                for key in columns
                if key not in {"id", "root_path", "rel_path"}
            ),
            *values.values(),
        )
        items.append(item(values))
    return {"indexed": len(items), "items": items, "errors": errors}


async def search(q="", aspect=None):
    words = q.casefold().strip().split()
    results = []
    for row in await repo.rows(
        "SELECT * FROM asset_library WHERE root_path=? ORDER BY rel_path",
        str(library_path()),
    ):
        if not row["size_bytes"] or not library_path(row["rel_path"]).is_file():
            continue
        entry = item(row, aspect)
        haystack = " ".join([entry.rel_path, entry.caption, *entry.tags]).casefold()
        if all(word in haystack for word in words) and (
            not aspect or entry.width and "aspect_mismatch" not in entry.quality_flags
        ):
            results.append(entry)
    return results


async def get(aid):
    rows = await repo.rows(
        "SELECT * FROM asset_library WHERE root_path=? AND id=?",
        str(library_path()),
        aid,
    )
    if not rows or not library_path(rows[0]["rel_path"]).is_file():
        raise HTTPException(404, "片库素材不存在")
    return item(rows[0])
