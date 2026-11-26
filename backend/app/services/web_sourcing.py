"""Bounded public web acquisition. All previews and player assets are project-owned files."""

import asyncio
import base64
import hashlib
import io
import logging
import re
import textwrap
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, urljoin, urlsplit
from uuid import uuid4

import anyio
import httpx
import trafilatura
from duckduckgo_search import DDGS
from fastapi import HTTPException
from lxml import html
from lxml.etree import ParserError
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import Error as BrowserError
from playwright.async_api import async_playwright

from app.core.auth import project_dir, resolve_safe_path
from app.core.config import ROOT, settings
from app.db import repository as repo
from app.media import proxy
from app.media.assets import FORMATS, LIMIT
from app.media.limits import project_files, slot
from app.media.renderer import launch
from app.media.worker import run_command
from app.schemas.asset import EXTENSIONS, MediaAsset
from app.schemas.timeline import TimelinePatchRequest
from app.services import asset_indexer
from app.services.model_router import router
from app.services.storage_manager import guard
from app.services.timeline_engine import RevisionConflict, engine
from app.services.uploads import CHUNK, register_media
from app.tools.web_search import public_stream

log = logging.getLogger(__name__)
UNKNOWN = "未注明，使用前核实授权"
MOCK_SOURCES = [
    (
        "article",
        "模型发布与评测方法",
        "https://reelforge.example/model-brief",
        "AI 模型 新闻 快报 发布 评测 人工智能 model news",
    ),
    (
        "image",
        "产品界面与功能概览",
        "https://reelforge.example/product",
        "产品 功能 发布 界面 product feature",
    ),
    (
        "video",
        "技术原理示意片段",
        "https://reelforge.example/explainer",
        "知识 科普 原理 技术 science",
    ),
]


def mock_hits(q, kind):
    hits = [
        {
            "kind": k,
            "title": t,
            "url": u,
            "license": "ReelForge 离线示例",
            "snippet": tags,
        }
        for k, t, u, tags in MOCK_SOURCES
        if kind in ("all", k)
        and any(w.casefold() in q.casefold() for w in tags.split())
    ]

    for hit in hits:
        title = escape(hit["title"])
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 160"><rect width="480" height="160" fill="#112c3e"/>'
            f'<text x="24" y="92" font-size="26" fill="white">{title}</text></svg>'
        )
        hit["thumbnail_url"] = "data:image/svg+xml," + quote(svg)
    return hits


async def pexels_search(client, query, kind, key):
    video = kind == "video"
    url = "https://api.pexels.com/" + ("videos/search" if video else "v1/search")
    response = await client.get(
        url, headers={"Authorization": key}, params={"query": query, "per_page": 5}
    )
    entries = response.raise_for_status().json()["videos" if video else "photos"]
    results = []
    for entry in entries:
        if video:
            files = [
                f
                for f in entry.get("video_files", [])
                if f.get("file_type") == "video/mp4" and f.get("link")
            ]
            if not files:
                continue
            media_url = min(files, key=lambda f: abs((f.get("width") or 0) - 1280))[
                "link"
            ]
        else:
            media_url = entry["src"]["large"]
        results.append(
            {
                "kind": kind,
                "title": entry.get("alt") or query,
                "url": entry["url"],
                "media_url": media_url,
                "license": "Pexels License",
            }
        )
    return results


async def pixabay_search(client, query, kind, key):
    video = kind == "video"
    response = await client.get(
        "https://pixabay.com/api/" + ("videos/" if video else ""),
        params={"key": key, "q": query, "per_page": 5},
    )
    return [
        {
            "kind": kind,
            "title": entry["tags"],
            "url": entry["pageURL"],
            "license": "Pixabay Content License",
            "media_url": entry["videos"]["medium"]["url"]
            if video
            else entry["webformatURL"],
        }
        for entry in response.raise_for_status().json()["hits"]
    ]


async def firecrawl_search(client, query, kind, key):
    response = await client.post(
        "https://api.firecrawl.dev/v2/search",
        headers={"Authorization": "Bearer " + key},
        json={"query": query, "limit": 5},
    )
    return [
        {
            "kind": "article",
            "title": entry["title"],
            "url": entry["url"],
            "snippet": entry.get("description", ""),
            "license": UNKNOWN,
        }
        for entry in response.raise_for_status().json()["data"]["web"]
    ]


SEARCH_PROVIDERS = (
    ({"image", "video"}, "pexels_api_key", pexels_search),
    ({"image", "video"}, "pixabay_api_key", pixabay_search),
    ({"all", "article"}, "firecrawl_api_key", firecrawl_search),
)


async def search(q, kind="all"):
    cfg = settings()
    if cfg.mock_llm:
        return mock_hits(q, kind)
    async with httpx.AsyncClient(timeout=5) as client:
        for kinds, credential, provider in SEARCH_PROVIDERS:
            key = getattr(cfg, credential)
            if not key or kind not in kinds:
                continue
            try:
                results = await provider(client, q, kind, key)
            except (httpx.HTTPError, KeyError, ValueError, TypeError):
                continue
            if results:
                return results

    def ddg():
        with DDGS(timeout=5) as ddgs:
            if kind == "image":
                return [
                    {
                        "kind": kind,
                        "title": x["title"],
                        "url": x["url"],
                        "media_url": x["image"],
                        "license": UNKNOWN,
                    }
                    for x in ddgs.images(q, license_image="Public", max_results=5)
                ]
            hits = (
                ddgs.videos(q, max_results=5)
                if kind == "video"
                else ddgs.text(q, max_results=5)
            )
            return [
                {
                    "kind": "video" if kind == "video" else "article",
                    "title": x["title"],
                    "url": x.get("href") or x["content"],
                    "snippet": x.get("body", ""),
                    "license": UNKNOWN,
                }
                for x in hits
            ]

    try:
        return await asyncio.to_thread(ddg)
    except Exception:
        log.info("Public search unavailable", exc_info=True)
        return []


async def chunks_from_file(path):
    async with await anyio.open_file(path, "rb") as source:
        while chunk := await source.read(CHUNK):
            yield chunk


async def write_chunks(chunks, path, limit):
    size = 0
    digest = hashlib.sha256()
    async with await anyio.open_file(path, "wb") as out:
        async for chunk in chunks:
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, "素材超过大小限制")
            await asyncio.to_thread(guard, len(chunk))
            await out.write(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def preview(title, facts, url):
    canvas = Image.new("RGB", (1280, 720), "#112c3e")
    draw = ImageDraw.Draw(canvas)
    fonts = [
        *(ROOT / "assets/fonts").glob("*.ttf"),
        *(ROOT / "assets/fonts").glob("*.otf"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    fontpath = next((p for p in fonts if p.is_file()), None)

    def font(size):
        return (
            ImageFont.truetype(str(fontpath), size)
            if fontpath
            else ImageFont.load_default(size)
        )

    draw.rectangle((64, 76, 74, 610), fill="#4ddcca")
    draw.text(
        (112, 80), urlsplit(url).hostname or "ReelForge", font=font(25), fill="#92dace"
    )
    draw.multiline_text(
        (112, 165),
        "\n".join(textwrap.wrap(title[:64], 20)[:3]),
        font=font(48),
        fill="white",
        spacing=12,
    )
    draw.multiline_text(
        (112, 405),
        "\n".join(textwrap.wrap(" ".join(facts)[:160], 34)[:4]),
        font=font(30),
        fill="#d2e5eb",
        spacing=9,
    )
    data = io.BytesIO()
    canvas.save(data, "PNG")
    return data.getvalue()


async def browser_document(url, raw, crawl):
    """Replay a validated document. Pin subresource requests as well as the top-level URL."""

    async def configure(page, context, **kwargs):
        async def intercept(route):
            request = route.request
            if request.url == url and request.resource_type == "document":
                return await route.fulfill(body=raw, content_type="text/html")
            if request.method != "GET" or request.resource_type not in {
                "script",
                "stylesheet",
                "image",
                "xhr",
                "fetch",
            }:
                return await route.abort()
            try:
                async with public_stream(request.url) as (response, _):
                    data = bytearray()
                    async for chunk in response.aiter_bytes(65536):
                        data.extend(chunk)
                        if len(data) > 2 * CHUNK:
                            return await route.abort()
                    return await route.fulfill(
                        body=bytes(data),
                        content_type=response.headers.get("content-type", "text/plain"),
                    )
            except (ValueError, OSError, httpx.HTTPError):
                await route.abort()

        await context.route("**/*", intercept)
        await context.route_web_socket("**/*", lambda ws: ws.close())
        return page

    async with slot("browser"):
        if crawl:
            try:
                from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

                async with AsyncWebCrawler() as crawler:
                    crawler.crawler_strategy.set_hook(
                        "on_page_context_created", configure
                    )
                    result = await crawler.arun(
                        url=url,
                        config=CrawlerRunConfig(
                            cache_mode=CacheMode.BYPASS, page_timeout=5000
                        ),
                    )
                    if result.success:
                        media = [
                            m["src"]
                            for kind in ("images", "videos")
                            for m in (result.media or {}).get(kind, [])
                            if m.get("src")
                        ]
                        return result.html, media, "crawl4ai", None
            except Exception:
                log.debug("Crawl4AI unavailable", exc_info=True)
        async with (
            async_playwright() as pw,
            await launch(pw) as browser,
            await browser.new_context(service_workers="block") as context,
        ):
            page = await context.new_page()
            await configure(page, context)
            await page.goto(url, wait_until="domcontentloaded", timeout=5000)
            return (
                await page.content(),
                [],
                "playwright",
                await page.screenshot(type="png"),
            )


async def extract(url, raw, use_browser):
    strategy, media, capture = "http", [], None
    local = not settings().is_cloud_2c2g()
    if use_browser is True or (local and use_browser is None):
        try:
            raw, media, strategy, capture = await browser_document(url, raw, local)
        except Exception:
            log.info("Browser extraction unavailable; using SSR", exc_info=True)
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            pass  # Let the HTML parser use the document charset.
    try:
        tree = html.fromstring(raw or "<html/>")
    except ParserError as exc:
        raise HTTPException(422, "网页缺少可提取的内容") from exc
    title = tree.xpath("string(//title)") or urlsplit(url).hostname
    media += tree.xpath(
        '//meta[@property="og:image"]/@content | //article//img/@src | //article//video/@src'
    )
    media = [urljoin(url, m) for m in media[:20]]
    text = await asyncio.to_thread(trafilatura.extract, raw) or ""
    if not text and settings().jina_api_key:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://r.jina.ai/" + url,
                headers={"Authorization": "Bearer " + settings().jina_api_key},
            )
            if response.is_success:
                text = response.text[:10000]
    if not text and not media and not capture and title == urlsplit(url).hostname:
        raise HTTPException(422, "网页缺少可用正文或画面")
    facts = [p for p in text.splitlines() if p.strip()][:6]
    try:
        extraction_slot = "crawler_extract"
        config = await router.route(extraction_slot)
        if "reader" in config.model.casefold() and "lm" in config.model.casefold():
            cleaned = await router.complete_text(
                extraction_slot,
                "将 HTML 清理为 Markdown，保留文章事实与引用。",
                raw[:24000].decode("utf-8", "replace")
                if isinstance(raw, bytes)
                else raw[:24000],
                lambda: text,
            )
            if isinstance(cleaned, str) and cleaned.strip():
                text = cleaned
            extraction_slot = "llm_director"
        data = await router.complete_json(
            extraction_slot,
            "从网页摘录最多六条原文事实，返回 facts 字符串数组。按相关性排列 media 中已有的图片/视频 URL。禁止编造。",
            {"title": title, "text": text[:10000], "media": media},
            lambda: {"facts": facts, "media": media},
        )
        if isinstance(data.get("facts"), list):
            facts = [x[:500] for x in data["facts"][:6] if isinstance(x, str)]
        if isinstance(data.get("media"), list):
            media = [m for m in data["media"] if m in media]
    except (HTTPException, ValueError, RuntimeError):
        pass
    return {
        "title": title,
        "facts": facts,
        "media": media,
        "strategy": strategy,
    }, capture


async def download(url, path):
    async with public_stream(url) as (response, final):
        mime = response.headers.get("content-type", "").split(";")[0].lower()
        limit = (
            settings().upload_max_mb * CHUNK
            if mime.startswith(
                ("video/", "image/", "audio/", "application/octet-stream")
            )
            else 2 * CHUNK
        )
        size, digest = await write_chunks(response.aiter_bytes(CHUNK), path, limit)
    return mime, final, size, digest


def inspect_file(path, name):
    try:
        with Image.open(path, formats=list(FORMATS)) as image:
            if image.width * image.height > 40_000_000:
                raise HTTPException(413, "图片像素过大")
            image.verify()
            return (
                "image",
                FORMATS[image.format],
                {"width": image.width, "height": image.height},
            )
    except (OSError, ValueError):
        pass
    ext = Path(name).suffix.lower().lstrip(".")
    kind = next((k for k in ("audio", "video") if ext in EXTENSIONS[k]), None)
    if kind:
        try:
            info = proxy.probe(path)
            if info["duration_ms"] and (kind == "audio" or info["width"]):
                return kind, ext, info
        except (ValueError, RuntimeError):
            pass
    raise HTTPException(422, "素材内容不是有效的图片、视频或音频")


async def publish(
    pid,
    path,
    name,
    size,
    digest,
    source_type,
    source_url=None,
    license=None,
    *,
    image_only=False,
    target=None,
):
    kind, ext, info = await asyncio.to_thread(
        inspect_file, path, "" if image_only else name
    )
    aid = uuid4().hex
    relative = f"media/{aid}.{ext}"
    patch = None
    if target:
        revision, track, clip = target
        if kind not in {"image", "video"}:
            raise HTTPException(422, "占位镜头需要图片或视频")
        patch = TimelinePatchRequest(
            base_revision=revision,
            summary="粘贴素材并替换占位镜头",
            ops=[
                {
                    "op": "update_clip",
                    "track": track,
                    "clip_id": clip.id,
                    "patch": {
                        "kind": kind + "_clip",
                        "asset_id": aid,
                        "source_state": source_type,
                        "prompt_hint": None,
                        "component_id": None,
                        "src": None,
                        "source_url": source_url,
                        "source_in_ms": 0,
                        "source_out_ms": None,
                        "speed": min(
                            1, info["duration_ms"] / (clip.end_ms - clip.start_ms)
                        )
                        if kind == "video" and info.get("duration_ms")
                        else 1,
                        "text": name,
                    },
                }
            ],
        )
    dest = resolve_safe_path(project_dir(pid), relative)
    dest.parent.mkdir(parents=True, exist_ok=True)
    path.replace(dest)
    try:
        return await register_media(
            pid,
            aid,
            kind,
            Path(name).name,
            relative,
            info,
            digest,
            size,
            source_type,
            patch=patch,
            source_url=source_url,
            license=license,
        )
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


async def store_bytes(path, data):
    async def parts():
        for i in range(0, len(data), CHUNK):
            yield data[i : i + CHUNK]

    return await write_chunks(
        parts(), path, min(LIMIT, settings().upload_max_mb * CHUNK)
    )


async def fetch(
    pid,
    url,
    *,
    license=None,
    use_browser=None,
    media_url=None,
    target=None,
    capture_only=False,
):
    await engine.get(pid)
    root = project_dir(pid)
    async with project_files(pid):
        with TemporaryDirectory(dir=root) as tmp:
            path = Path(tmp) / "source"
            details = {"title": url, "facts": [], "media": [], "strategy": "http"}
            if settings().mock_llm:
                hit = next((r for r in MOCK_SOURCES if r[2] == url), None)
                if not hit:
                    raise HTTPException(404, "离线模式未收录该 URL")
                details.update(title=hit[1], facts=["离线示例素材"], strategy="mock")
                license = "ReelForge 离线示例"
                name = hit[1] + ".png"
                size, digest = await store_bytes(
                    path, preview(hit[1], details["facts"], url)
                )
                if hit[0] == "video" and not capture_only:
                    still = path.with_suffix(".png")
                    path.replace(still)
                    async with slot("render"):
                        await run_command(
                            [
                                "ffmpeg",
                                "-nostdin",
                                "-loglevel",
                                "error",
                                "-loop",
                                "1",
                                "-i",
                                still,
                                "-t",
                                "2",
                                "-c:v",
                                "libx264",
                                "-pix_fmt",
                                "yuv420p",
                                "-threads",
                                "2",
                                "-f",
                                "mp4",
                                path,
                            ]
                        )
                    name = hit[1] + ".mp4"
                    size = path.stat().st_size
                    with path.open("rb") as src:
                        digest = hashlib.file_digest(src, "sha256").hexdigest()
            else:
                try:
                    mime, final, size, digest = await download(media_url or url, path)
                    name = Path(urlsplit(final).path).name or "网页预览"
                    media_ext = {
                        "video/mp4": ".mp4",
                        "video/webm": ".webm",
                        "video/quicktime": ".mov",
                        "audio/mpeg": ".mp3",
                    }.get(mime)
                    if media_ext and not Path(name).suffix:
                        name += media_ext
                    if capture_only:
                        if mime not in {"text/html", "application/xhtml+xml"}:
                            raise HTTPException(422, "网页截图需要 HTML 页面")
                        _, _, strategy, capture = await browser_document(
                            final, path.read_bytes(), crawl=False
                        )
                        name = "网页截图.png"
                        details["strategy"] = strategy
                        size, digest = await store_bytes(path, capture)
                    elif mime in {"text/html", "application/xhtml+xml", "text/plain"}:
                        details, capture = await extract(
                            final, path.read_bytes(), use_browser
                        )
                        picked = False
                        for candidate in details["media"][:3]:
                            try:
                                _, candidate_url, size, digest = await download(
                                    candidate, path
                                )
                                name = Path(urlsplit(candidate_url).path).name
                                await asyncio.to_thread(inspect_file, path, name)
                                picked = True
                                break
                            except (
                                httpx.HTTPError,
                                OSError,
                                ValueError,
                                HTTPException,
                            ) as exc:
                                if (
                                    isinstance(exc, HTTPException)
                                    and exc.status_code == 507
                                ):
                                    raise
                        if not picked:
                            name = details["title"][:100] + ".png"
                            size, digest = await store_bytes(
                                path,
                                capture
                                or preview(details["title"], details["facts"], final),
                            )
                except (BrowserError, httpx.HTTPError, OSError, ValueError) as exc:
                    raise HTTPException(422, "无法抓取该公开网页或媒体") from exc
            asset = await publish(
                pid,
                path,
                name,
                size,
                digest,
                "web_fetched",
                url,
                license or UNKNOWN,
                target=target,
            )
            return {"asset": asset, **details}


async def attach_library(pid, aid):
    entry = await asset_indexer.get(aid)
    await engine.get(pid)
    async with project_files(pid):
        existing = await repo.rows(
            "SELECT * FROM media_assets WHERE project_id=? AND sha256=? AND source_type='local_matched'",
            pid,
            entry.sha256,
        )

        if (
            existing
            and resolve_safe_path(project_dir(pid), existing[0]["rel_path"]).is_file()
        ):
            return MediaAsset.model_validate(existing[0])
        with TemporaryDirectory(dir=project_dir(pid)) as tmp:
            path = Path(tmp) / "local"
            size, digest = await write_chunks(
                chunks_from_file(asset_indexer.library_path(entry.rel_path)),
                path,
                settings().upload_max_mb * CHUNK,
            )
            if digest != entry.sha256:
                raise HTTPException(409, "片库文件已更改，请重新扫描")
            return await publish(
                pid, path, entry.filename, size, digest, "local_matched"
            )


async def paste(pid, body):
    doc = await engine.get(pid)
    clip = None
    if body.slot_clip_id:
        if body.base_revision is not None and body.base_revision != doc.revision:
            raise RevisionConflict(doc.revision)
        clip = next(
            (c for c in getattr(doc.tracks, body.track) if c.id == body.slot_clip_id),
            None,
        )
        if not clip or clip.kind != "placeholder":
            raise HTTPException(409, "所选镜头已不是占位镜头")
    target = (doc.revision, body.track, clip) if clip else None
    if body.url:
        asset = (await fetch(pid, str(body.url), target=target))["asset"]
    else:
        match = re.fullmatch(
            r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)",
            body.image_data_url or "",
        )
        if not match:
            raise HTTPException(422, "需要 PNG、JPEG 或 WebP 剪贴板图片")
        try:
            data = base64.b64decode(match[2], validate=True)
        except ValueError as exc:
            raise HTTPException(422, "图片编码无效") from exc
        async with project_files(pid):
            with TemporaryDirectory(dir=project_dir(pid)) as tmp:
                path = Path(tmp) / "paste"
                size, digest = await store_bytes(path, data)
                asset = await publish(
                    pid,
                    path,
                    body.filename or "剪贴板." + match[1],
                    size,
                    digest,
                    "local_matched",
                    image_only=True,
                    target=target,
                )
    return {"asset": asset, "timeline": await engine.get(pid) if target else None}
