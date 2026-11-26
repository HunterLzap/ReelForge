from pathlib import Path
from secrets import compare_digest

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from app.core.config import settings


class UnsafePath(ValueError):
    pass


def resolve_safe_path(base_dir: Path, candidate: str | Path) -> Path:
    base = Path(base_dir).resolve()
    candidate = Path(candidate)
    path = (base / candidate).resolve()
    if ".." in candidate.parts or not path.is_relative_to(base):
        raise UnsafePath("路径超出允许的目录")
    return path


def project_dir(pid: str) -> Path:
    if Path(pid).name != pid or pid in {"", ".", ".."}:
        raise HTTPException(422, "无效的项目目录")
    root = settings().workspace_dir
    path = resolve_safe_path(root, pid)
    if path != root / pid:
        raise HTTPException(422, "项目目录不能是符号链接")
    return path


async def authenticate(request: Request, call_next):
    path = request.url.path
    token = settings().access_token
    if (
        token
        and path != "/api/system/health"
        and path.startswith(("/api/", "/workspace/"))
    ):
        scheme, _, bearer = request.headers.get("authorization", "").partition(" ")
        candidates = [request.query_params.get("token", "")]
        if scheme.lower() == "bearer":
            candidates.append(bearer)
        if not any(
            compare_digest(candidate.encode(), token.encode())
            for candidate in candidates
        ):
            return JSONResponse(
                {"detail": "需要有效的访问令牌"},
                401,
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)
