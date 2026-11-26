"""ReelForge stdio entry point for local agent clients."""

from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import StringConstraints

from app.agents.director import RULES
from app.core.config import settings
from app.db.database import init
from app.main import app
from app.schemas.research import Evidence, SourceItem
from app.schemas.storyboard import SceneItem, StoryboardScript

mcp = FastMCP("ReelForge")
Id = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


async def request(method, path, body=None, files=None):
    url = settings().reelforge_api_base.rstrip("/") + "/api/projects" + path
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(None, connect=2), trust_env=False
        ) as client:
            result = await client.request(method, url, json=body, files=files)
    except httpx.ConnectError:
        await init()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            result = await client.request(method, url, json=body, files=files)
    if result.is_error:
        raise ValueError(f"HTTP {result.status_code} {result.text}")
    return result.json()


@mcp.tool()
def get_storyboard_schema():
    """查看九种模板字段、字数限制、各画幅建议幕数与写作规范。首幕必须是唯一封面。"""
    return {
        "schema": StoryboardScript.model_json_schema(),
        "formats": {
            k: {"min_scenes": a, "max_scenes": b, "guide": c}
            for k, (a, b, c) in RULES.items()
        },
        "copy_guide": "标题建议 12–20 字，标签 2–8 字，正文保持短句。每幕引用已保存的 source_ids。",
    }


@mcp.tool()
async def create_project(
    topic: str,
    target_format: str = "video_16_9",
    theme: str = "editorial_dark",
    voice: str = "",
    brand_label: str = "",
):
    """创建等待外部协作的项目，返回项目编号与浏览器工作台直达链接。"""
    p = await request(
        "POST",
        "",
        {
            "topic": topic,
            "target_format": target_format,
            "theme": theme,
            "voice": voice,
            "brand_label": brand_label,
            "execution_mode": "mcp",
        },
    )
    return {
        "project_id": p["id"],
        "workbench_url": "http://127.0.0.1:5173/?project=" + p["id"],
    }


@mcp.tool()
async def save_research(
    project_id: Id,
    outline: list[str],
    sources: list[SourceItem],
    key_facts: list[Evidence],
    data_points: list[Evidence],
):
    """保存大纲、可查证的来源及带来源编号的事实和数据。"""
    return await request(
        "POST",
        f"/{project_id}/research",
        {
            "outline": outline,
            "sources": [s.model_dump(mode="json") for s in sources],
            "key_facts": [s.model_dump() for s in key_facts],
            "data_points": [s.model_dump() for s in data_points],
        },
    )


@mcp.tool()
async def set_storyboard(project_id: Id, scenes: list[SceneItem]):
    """校验并替换完整分镜。局部编辑用 update_scene 保留其余幕缓存。"""
    return await request(
        "PUT",
        f"/{project_id}/storyboard",
        {"scenes": [s.model_dump() for s in scenes]},
    )


@mcp.tool()
async def update_scene(
    project_id: Id,
    scene_id: Id,
    template_type: str | None = None,
    narration: str | None = None,
    visual_payload: dict | None = None,
    source_ids: list[str] | None = None,
):
    """修改指定分镜的给定字段并标记 DIRTY，scene_id 可从项目状态取得。"""
    changes = {
        "template_type": template_type,
        "narration": narration,
        "visual_payload": visual_payload,
        "source_ids": source_ids,
    }
    return await request(
        "PATCH",
        f"/{project_id}/scenes/{scene_id}",
        {k: v for k, v in changes.items() if v is not None},
    )


@mcp.tool()
async def add_scene(project_id: Id, scene: SceneItem):
    """在末尾新增一幕并返回 scene_id。"""
    return await request("POST", f"/{project_id}/scenes", scene.model_dump())


@mcp.tool()
async def delete_scene(project_id: Id, scene_id: Id):
    """删除指定非封面分镜。"""
    return await request("DELETE", f"/{project_id}/scenes/{scene_id}")


@mcp.tool()
async def reorder_scenes(project_id: Id, scene_ids: list[Id]):
    """按全部分镜编号重排顺序，封面保留在首位。"""
    return await request(
        "PUT", f"/{project_id}/scenes/reorder", {"scene_ids": scene_ids}
    )


@mcp.tool()
async def render_project(project_id: Id, rebuild_only: bool = False):
    """等待成片或图文包导出，返回绝对路径、分辨率、时长和缓存统计。"""
    return await request(
        "POST", f"/{project_id}/render", {"wait": True, "rebuild_only": rebuild_only}
    )


@mcp.tool()
async def rebuild_project(project_id: Id):
    """重新导出已完成项目，复用内容未变的分镜。"""
    return await render_project(project_id, True)


@mcp.tool()
async def get_project_status(project_id: Id):
    """查询状态、各幕内容和编号、预览地址及产物。"""
    return await request("GET", f"/{project_id}/status")


@mcp.tool()
async def attach_image(project_id: Id, file_path: str):
    """导入用户指定的本地 PNG、JPG 或 WebP，返回可用于分镜的 image_asset 编号。"""
    from pathlib import Path

    from app.media.assets import LIMIT

    path = Path(file_path).expanduser()
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise ValueError("需要小于等于 10 MB 的图片文件")
    return await request(
        "POST", f"/{project_id}/assets", files={"file": (path.name, path.read_bytes())}
    )


@mcp.tool()
async def clone_project(
    project_id: Id,
    target_format: str,
    topic: str | None = None,
    theme: str | None = None,
):
    """复制资料、图片与分镜，在新项目切换画幅。"""
    return await request(
        "POST",
        f"/{project_id}/clone",
        {"target_format": target_format, "topic": topic, "theme": theme},
    )


@mcp.tool()
async def cancel_project(project_id: Id):
    """停止 Web 工作台正在执行的任务。"""
    return await request("POST", f"/{project_id}/cancel")


if __name__ == "__main__":
    mcp.run(transport="stdio")
