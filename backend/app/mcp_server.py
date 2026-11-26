"""ReelForge stdio entry point for local agent clients."""

from typing import Annotated
from urllib.parse import quote, urlencode

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import StringConstraints

from app.agents.director import RULES
from app.core.config import settings
from app.db.database import init
from app.main import app
from app.schemas.research import Evidence, SourceItem
from app.schemas.review_pin import BBox
from app.schemas.storyboard import SceneItem, StoryboardScript
from app.schemas.timeline import Aspect, TimelineOp, Track

mcp = FastMCP("ReelForge")
Id = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


async def request(method, path, body=None, files=None, *, prefix="/api/projects"):
    url = settings().reelforge_api_base.rstrip("/") + prefix + path
    headers = (
        {"Authorization": "Bearer " + settings().access_token}
        if settings().access_token
        else {}
    )
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(None, connect=2), trust_env=False
        ) as client:
            result = await client.request(
                method, url, json=body, files=files, headers=headers
            )
    except httpx.ConnectError:
        await init()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            result = await client.request(
                method, url, json=body, files=files, headers=headers
            )
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


@mcp.tool()
async def list_skills():
    """列出已安装的编导技能与可用动效模板。"""
    return await request("GET", "/skills", prefix="/api")


@mcp.tool()
async def get_timeline(project_id: Id):
    """读取工程的五轨时间轴与当前修订号。"""
    return await request("GET", f"/{project_id}/timeline")


@mcp.tool()
async def patch_timeline(
    project_id: Id,
    base_revision: int,
    ops: list[TimelineOp],
    summary: str,
    author: str = "external_mcp",
    review_pin_id: str | None = None,
):
    """基于指定修订原子应用编辑操作。"""
    return await request(
        "POST",
        f"/{project_id}/timeline/patch",
        {
            "base_revision": base_revision,
            "summary": summary,
            "author": "external_mcp" if author == "mcp_agent" else author,
            "review_pin_id": review_pin_id,
            "ops": [op.model_dump() for op in ops],
        },
    )


@mcp.tool()
async def undo_timeline(project_id: Id, base_revision: int | None = None):
    """撤销上次编辑，返回新修订。"""
    return await request(
        "POST", f"/{project_id}/timeline/undo", {"base_revision": base_revision}
    )


@mcp.tool()
async def list_review_pins(project_id: Id):
    """读取审片时间、框选区域、批注及截图地址。"""
    return await request("GET", f"/{project_id}/pins")


@mcp.tool()
async def export_timeline(project_id: Id):
    """等待多轨成片导出并返回校验结果。"""
    return await request("POST", f"/{project_id}/timeline/export")


@mcp.tool()
async def redo_timeline(project_id: Id, base_revision: int | None = None):
    """重做上次撤销的时间轴编辑。"""
    return await request(
        "POST", f"/{project_id}/timeline/redo", {"base_revision": base_revision}
    )


@mcp.tool()
async def create_review_pin(
    project_id: Id,
    time_ms: int,
    note: str,
    bbox: BBox | None = None,
    track: Track | None = None,
    clip_id: str | None = None,
    frame_data_url: str | None = None,
    revision: int | None = None,
):
    """在指定时间点保存画框与批注，可提供 PNG 截帧。"""
    return await request(
        "POST",
        f"/{project_id}/pins",
        {
            "time_ms": time_ms,
            "note": note,
            "bbox": bbox.model_dump() if bbox else None,
            "track": track,
            "clip_id": clip_id,
            "frame_data_url": frame_data_url,
            "revision": revision,
            "author": "external_mcp",
        },
    )


@mcp.tool()
async def resolve_review_pin(
    project_id: Id,
    pin_id: Id,
    resolved_by_revision: int | None = None,
    summary: str | None = None,
):
    """将批注标为已解决，可以关联修订与处理说明。"""
    return await request(
        "PATCH",
        f"/{project_id}/pins/{pin_id}",
        {
            "status": "resolved",
            "author": "external_mcp",
            "resolution_summary": summary,
            "resolved_by_revision": resolved_by_revision,
        },
    )


@mcp.tool()
async def ai_fix_pin(project_id: Id, pin_id: Id, base_revision: int | None = None):
    """按截帧、坐标和批注自动修改时间轴，返回变更摘要。"""
    return await request(
        "POST",
        f"/{project_id}/pins/{pin_id}/ai-fix",
        {"base_revision": base_revision, "author": "external_mcp"},
    )


@mcp.tool()
async def index_local_library(path: str = "", aspect: Aspect | None = None):
    """索引 LIBRARY_ROOT 内的素材目录。"""
    return await request(
        "POST", "/library/index", {"path": path, "aspect": aspect}, prefix="/api"
    )


@mcp.tool()
async def search_media(query: str = "", project_id: Id | None = None):
    """按名称搜索项目素材；省略工程编号时搜索片库标签、名称和描述。"""
    if project_id:
        assets = await request("GET", f"/{project_id}/media")
        return [
            item for item in assets if query.casefold() in item["filename"].casefold()
        ]
    return await request(
        "GET", "/library/search?" + urlencode({"q": query}), prefix="/api"
    )


@mcp.tool()
async def transcribe_media(
    project_id: Id,
    asset_id: Id | None = None,
    base_revision: int | None = None,
    sync_subtitles: bool = True,
    hotwords: list[str] | None = None,
):
    """转写工程媒体，可同步字幕。"""
    return await request(
        "POST",
        f"/{project_id}/transcribe",
        {
            "asset_id": asset_id,
            "base_revision": base_revision,
            "sync_subtitles": sync_subtitles,
            "hotwords": hotwords,
        },
    )


@mcp.tool()
async def auto_rough_cut(
    project_id: Id,
    apply: bool = False,
    base_revision: int | None = None,
    buffer_ms: int = 80,
    issue_ids: list[str] | None = None,
):
    """预览口癖、停顿和重说建议；apply=true 时提交粗剪。"""
    return await request(
        "POST",
        f"/{project_id}/rough-cut",
        {
            "apply": apply,
            "base_revision": base_revision,
            "buffer_ms": buffer_ms,
            "issue_ids": issue_ids,
        },
    )


@mcp.tool()
async def get_storage_status():
    """查询工作区容量、缓存明细与配额。"""
    return await request("GET", "/system/storage", prefix="/api")


@mcp.tool()
async def get_system_capabilities():
    """探测硬件、工具与当前部署护栏。"""
    return await request("POST", "/system/probe", prefix="/api")


@mcp.tool()
async def read_skill(skill_id: str):
    """读取技能指南和组件字段。"""
    return await request("GET", "/skills/" + quote(skill_id, safe=""), prefix="/api")


@mcp.tool()
async def get_transcript(project_id: Id):
    """读取当前文稿、逐词时间和粗剪建议。"""
    return await request("GET", f"/{project_id}/transcript")


@mcp.tool()
async def edit_transcript_cuts(
    project_id: Id, base_revision: int, delete_word_ids: list[str], buffer_ms: int = 80
):
    """根据保留缓冲和删词列表重新剪辑。"""
    return await request(
        "POST",
        f"/{project_id}/rough-cut",
        {
            "apply": True,
            "base_revision": base_revision,
            "delete_word_ids": delete_word_ids,
            "buffer_ms": buffer_ms,
        },
    )


@mcp.tool()
async def update_subtitles(project_id: Id, base_revision: int, clip_id: str, text: str):
    """更新一个字幕片段并写入修订历史。"""
    return await request(
        "PATCH",
        f"/{project_id}/timeline",
        {
            "base_revision": base_revision,
            "summary": "更新字幕文字",
            "author": "external_mcp",
            "ops": [
                {
                    "op": "update_clip",
                    "track": "subtitle",
                    "clip_id": clip_id,
                    "patch": {"text": text},
                }
            ],
        },
    )


@mcp.tool()
async def search_local_assets(query: str = ""):
    """搜索本地索引的片库素材。"""
    return await search_media(query)


@mcp.tool()
async def crawl_web_media(project_id: Id, url: str):
    """采集指定网页中的媒体并保存来源。"""
    return await request("POST", f"/{project_id}/sourcing/fetch", {"url": url})


@mcp.tool()
async def capture_webpage_shot(project_id: Id, url: str):
    """使用浏览器抓取网页画面到项目素材库。"""
    return await request(
        "POST", f"/{project_id}/sourcing/fetch", {"url": url, "capture_only": True}
    )


@mcp.tool()
async def attach_asset(project_id: Id, item_id: str):
    """将片库索引中的素材导入项目。"""
    return await request(
        "POST", f"/{project_id}/library/{quote(item_id, safe='')}/import"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
