import base64
import os
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import Error, sync_playwright

from app.core.config import ROOT, settings

SIZES = {
    "video_16_9": (1920, 1080),
    "video_9_16": (1080, 1920),
    "cards_3_4": (1080, 1440),
}
env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates"),
    autoescape=select_autoescape(),
)


def render(folder, project, scene, count):
    if os.name == "nt":
        # Node trusts TEMP even when the directory is read-only. Python probes it.
        temp = Path(tempfile.gettempdir())
        if temp == Path.cwd():
            temp = settings().workspace_dir / ".tmp"
            temp.mkdir(parents=True, exist_ok=True)
        os.environ["TMP"] = os.environ["TEMP"] = str(temp)
    width, height = SIZES[project["target_format"]]
    fonts = sorted(
        f
        for f in (ROOT / "assets/fonts").glob("*")
        if f.suffix.lower() in {".ttf", ".otf", ".woff2"}
    )
    font_data = base64.b64encode(fonts[0].read_bytes()).decode() if fonts else ""
    html = env.get_template(scene["template_type"] + ".html").render(
        p=scene["visual_payload"],
        theme=project["theme"],
        index=scene["order_index"],
        count=count,
        topic=project["topic"],
        font_data=font_data,
    )
    (folder / "card.html").write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Error:
            browser = pw.chromium.launch(channel="msedge")
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html)
            page.evaluate("document.fonts.ready")
            page.evaluate("""() => {
              const content=document.querySelector('article'), box=document.querySelector('main');
              let size=parseFloat(getComputedStyle(content).fontSize);
              while ((content.scrollHeight>box.clientHeight || content.scrollWidth>box.clientWidth) && size>10) {
                content.style.fontSize=(size-=2)+'px';
              }
            }""")
            page.screenshot(path=str(folder / "card.png"))
        finally:
            browser.close()
