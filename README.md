# ReelForge · 映铸

本地内容生产工作台。输入选题后，依次完成采编、核查、分镜、渲染、合成。横屏和竖屏项目导出 1080P MP4，图文项目导出 1080 × 1440 PNG 和 ZIP。接口与数据契约见 [项目计划](project_plan.md)。

## 安装

准备 Python 3.11+、Node.js 20+、带 libass/libx264/AAC 和 ffprobe 的 FFmpeg 6+。在项目根目录创建环境：

```sh
python -m venv .venv
```

PowerShell 执行 `.\.venv\Scripts\Activate.ps1`；macOS/Linux 执行 `source .venv/bin/activate`。继续安装：

```sh
python -m pip install -e ./backend
python -m playwright install chromium
cd frontend
npm ci
cd ..
```

复制 `.env.example` 为根目录 `.env`。离线演示设置 `MOCK_LLM=true`。Mock 从内置样例采编，资料 URL 为示例，旁白使用随依赖安装的 eSpeak NG 普通话离线语音。系统需有可用的中文字体。可在 `assets/fonts/` 放入自有授权字体，在 `assets/bgm/` 放入可用的背景音乐；默认各取按文件名排序的第一项。

## 启动

在已激活环境的终端：

```sh
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开终端：

```sh
cd frontend
npm run dev
```

打开 http://localhost:5173 。开发服务器转发 REST、SSE 和产物请求。API 文档位于 http://127.0.0.1:8000/docs 。服务使用单 worker，工作区与数据库的相对路径均相对于项目根目录。

## 制作与修改

1. 新建项目，填写选题并选择规格、视觉主题、配音与审批方式。
2. 使用手动审批时，先阅读大纲和事实核查，再确认分镜。核查打回时自动补查，达到次数上限后显示错误。
3. 在分镜面板编辑旁白或视觉 JSON。首幕固定为封面。完成后点击「重新渲染改动分镜」，缓存命中的分镜继续复用。
4. 在成品预览中播放或下载；「资料溯源」提供原始链接与 Markdown 清单。

所有产物保存在 `workspace/<项目ID>/`。视频为 `output/final.mp4`，图文为 `output/cards/*.png` 和 `output/cards.zip`。项目同时保存三个 JSON 快照，各幕保留 HTML、PNG 和缓存元数据，视频项目另存音频、字幕与单幕剪辑。

## CLI 与验收

PowerShell 先设置 `$env:MOCK_LLM='true'`，macOS/Linux 执行 `export MOCK_LLM=true`。在 backend 目录运行：

```sh
ruff check app ../tests
pytest ../tests -v
python -m app.cli demo --topic "2026上海租房避坑"
python -m app.cli demo --topic "图文示例" --target-format cards_3_4
python -m app.cli rebuild <项目ID>
```

在 frontend 目录运行 `npm run build`，静态产物在 `dist/`。测试强制使用独立临时数据库和 Mock 模式，媒体测试实际启动浏览器与 FFmpeg。

## 真实采编

在根目录 `.env` 设置 `MOCK_LLM=false`，配置 `LLM_BASE_URL`、`LLM_MODEL` 与 `LLM_API_KEY` 后重启服务。采编使用 DuckDuckGo 与网页正文，三个文本节点共享 OpenAI 兼容客户端。edge-tts 配音需要网络；画面、字幕烧录和剪辑在本机执行。可按供应商费率设置 `INPUT_CNY_PER_MILLION` 与 `OUTPUT_CNY_PER_MILLION`（元/百万 token），默认费率为零。不要用真实模式运行验收或联调。
