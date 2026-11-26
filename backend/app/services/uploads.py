import hashlib
import re
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

import anyio
from fastapi import HTTPException, UploadFile
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.media.assets import LIMIT
from app.services.storage_manager import guard

UPLOAD_ROUTE = re.compile(
    r"/api/(?:media/upload|projects/[^/]+/(?:scenes/[^/]+/)?assets)/?"
)
CHUNK = 1024 * 1024


@asynccontextmanager
async def staged_upload(file: UploadFile, directory: Path, limit=None):
    maximum = min(
        limit or settings().upload_max_mb * CHUNK, settings().upload_max_mb * CHUNK
    )
    if file.size is not None and file.size > maximum:
        raise HTTPException(413, "文件超过上传大小限制")
    await anyio.to_thread.run_sync(guard, file.size or 0)
    directory.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as tmp:
        path = Path(tmp.name)
    size = 0
    digest = hashlib.sha256()
    try:
        async with await anyio.open_file(path, "wb") as dest:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > maximum:
                    raise HTTPException(413, "文件超过上传大小限制")
                digest.update(chunk)
                await dest.write(chunk)
        yield path, size, digest.hexdigest()
    finally:
        path.unlink(missing_ok=True)


class UploadGuard:
    """Reject requests before multipart parsing can spool a large body to disk."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and UPLOAD_ROUTE.fullmatch(scope["path"])
        ):
            try:
                await anyio.to_thread.run_sync(guard)
            except HTTPException as exc:
                return await JSONResponse(
                    {"detail": exc.detail}, status_code=exc.status_code
                )(scope, receive, send)
            maximum = settings().upload_max_mb * CHUNK
            if scope["path"] != "/api/media/upload":
                maximum = min(maximum, LIMIT)
            # Allow multipart headers and small fields. staged_upload enforces the exact file limit.
            limited = RequestBodyLimitMiddleware(
                self.app, max_body_size=maximum + 64 * 1024
            )
            return await limited(scope, receive, send)
        return await self.app(scope, receive, send)
