import asyncio
import base64
import os
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import Error, async_playwright

from app.core.config import ROOT, settings

SIZES = {
    "video_16_9": (1920, 1080),
    "video_9_16": (1080, 1920),
    "cards_3_4": (1080, 1440),
}
SECTIONS = {
    "cover": "封面专题",
    "hero_stat": "关键数字",
    "stat_chart": "数据观察",
    "compare_split": "对照分析",
    "timeline": "行动路径",
    "big_quote": "编辑摘录",
    "bullet_list": "现场笔记",
    "checklist": "核对清单",
}
env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates"),
    autoescape=select_autoescape(),
)

FIT = """() => {
 const article=document.querySelector("article"), main=article.parentElement;
 let lo=1,hi=parseFloat(getComputedStyle(article).fontSize);
 const safe=main.getBoundingClientRect();
 const ranges=[];
 const walker=document.createTreeWalker(article,NodeFilter.SHOW_TEXT);
 while(walker.nextNode()){
   if(!walker.currentNode.textContent.trim())continue;
   const range=document.createRange();range.selectNodeContents(walker.currentNode);ranges.push(range);
 }
 const fits=()=>article.getBoundingClientRect().height<=safe.height && article.scrollWidth<=safe.width+1
   && ranges.every(range=>Array.from(range.getClientRects()).every(r=>!r.width ||
       (r.top>=safe.top-1 && r.bottom<=safe.bottom+1 && r.left>=safe.left-1 && r.right<=safe.right+1)));
 for(let i=0;i<12;i++){
   let mid=(lo+hi)/2; article.style.fontSize=mid+'px';
   if(fits())lo=mid;else hi=mid;
 }
 article.style.fontSize=lo+'px';
 if(!fits())throw Error('卡片内容超出安全区');
}"""


def html(project, scene, count, font_data=""):
    target = project["target_format"]
    kind = scene["template_type"]
    bars = scene["visual_payload"].get("bars", [])
    low = min([0] + [b["value"] for b in bars])
    high = max([0] + [b["value"] for b in bars])
    scale = max(abs(low), high) or 1
    span = high / scale - low / scale or 1
    chart = [
        {
            **b,
            "x": 100 * (min(0, b["value"] / scale) - low / scale) / span,
            "width": 100 * abs(b["value"] / scale) / span,
            "color": b["accent"],
        }
        for b in bars
    ]
    return env.get_template(kind + ".html").render(
        p=scene["visual_payload"],
        target_format=target,
        theme=project["theme"],
        section=SECTIONS[kind],
        kind=kind,
        chart=chart,
        ticks=[(1 - i / 4) * low + (i / 4) * high for i in range(5)],
        brand=project.get("brand_label", ""),
        topic=project["topic"],
        index=scene["order_index"],
        count=count,
        font_data=font_data,
    )


async def _batch(project, jobs, count):
    fonts = sorted(
        p
        for p in (ROOT / "assets/fonts").iterdir()
        if p.suffix.lower() in {".ttf", ".otf", ".woff2"}
    )
    font = base64.b64encode(fonts[0].read_bytes()).decode() if fonts else ""
    width, height = SIZES[project["target_format"]]
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch()
        except Error:
            browser = await pw.chromium.launch(channel="msedge")
        context = await browser.new_context(viewport={"width": width, "height": height})
        limit = asyncio.Semaphore(3)

        async def capture(folder, scene):
            async with limit:
                page = await context.new_page()
                try:
                    await page.set_content(html(project, scene, count, font))
                    await page.evaluate("document.fonts.ready")
                    await page.evaluate(FIT)
                    (folder / "card.html").write_text(
                        await page.content(), encoding="utf-8"
                    )
                    await page.screenshot(path=str(folder / "card.png"))
                finally:
                    await page.close()

        try:
            await asyncio.gather(*(capture(path, s) for path, s in jobs))
        finally:
            await browser.close()


def render_batch(project, jobs, count):
    if not jobs:
        return
    if os.name == "nt":
        temp = Path(tempfile.gettempdir())
        if temp == Path.cwd():
            temp = settings().workspace_dir / ".tmp"
            temp.mkdir(parents=True, exist_ok=True)
        os.environ["TEMP"] = os.environ["TMP"] = str(temp)
        with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
            runner.run(_batch(project, jobs, count))
    else:
        asyncio.run(_batch(project, jobs, count))


def render(folder, project, scene, count):
    render_batch(project, [(folder, scene)], count)
