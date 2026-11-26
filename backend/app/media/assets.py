import hashlib
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image

from app.core.config import settings

LIMIT = 10 * 1024 * 1024
ASSET_PATTERN = r"^[a-f0-9]{64}\.(png|jpg|webp)$"
FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


def asset_path(pid, name):
    root = settings().workspace_dir / pid / "assets"
    if not re.fullmatch(ASSET_PATTERN, name) or root.resolve() != root:
        raise ValueError("无效的项目图片")
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("项目中没有这张图片")
    return path


def store(pid, data):
    if len(data) > LIMIT:
        raise ValueError("图片超过 10 MB")
    directory = settings().workspace_dir / pid / "assets"
    if directory.resolve() != directory:
        raise ValueError("无效的素材目录")
    directory.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as tmp:
        tmp.write(data)
    path = Path(tmp.name)
    try:
        return store_file(pid, path, hashlib.sha256(data).hexdigest())
    finally:
        path.unlink(missing_ok=True)


def store_file(pid, path, digest):
    try:
        with Image.open(path, formats=list(FORMATS)) as img:
            ext = FORMATS[img.format]
            if img.width * img.height > 40_000_000:
                raise ValueError("图片像素过大")
            img.verify()
        with Image.open(path) as img:
            img.load()
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("请上传有效的 PNG、JPEG 或 WebP 图片") from exc
    name = digest + "." + ext
    path.replace(path.parent / name)
    return {"asset_id": name, "url": f"/workspace/{pid}/assets/{name}"}


def validate_image(pid, payload):
    if name := getattr(payload, "image_asset", None):
        asset_path(pid, name)
