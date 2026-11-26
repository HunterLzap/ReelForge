# ReelForge · 映铸

本地内容生产工作台。输入选题后，依次完成采编、核查、分镜、渲染、合成。横屏和竖屏项目导出 1080P MP4，图文项目导出 1080 × 1440 PNG 和 ZIP。架构总纲与工程指引见 [agent/agent.md](agent/agent.md)。

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
3. 在中间画布选择缩略图，使用右侧表单编辑九种模板、试听旁白、按意图润色。预览显示未保存的视觉改动；保存后可增删、调序并点击「重渲染并导出」。封面固定在首位，页码受影响的幕会随编排更新。
4. 在成品预览中播放或下载；「资料溯源」提供原始链接与 Markdown 清单。

所有产物保存在 `workspace/<项目ID>/`。视频为 `output/final.mp4`，图文为 `output/cards/*.png` 和 `output/cards.zip`。项目同时保存三个 JSON 快照，各幕保留 HTML、PNG 和缓存元数据，视频项目另存音频、字幕与单幕剪辑。

## v2.0 创作台

- 在新建项目的「高级选项」中粘贴笔记或网页地址。勾选「仅使用自带资料」后，采编只读取这些材料。离线模式保存 URL 与随附摘要，纯文本来源直接显示为用户笔记。
- 在分镜属性的「画面内容」选择图片卡，或给封面添加配图。PNG、JPEG 和 WebP 每张最多 10 MB。图片保存在项目内，克隆时一并复制。可在创建时选择字幕、语速和转场，通过 `PATCH /api/projects/{id}/settings` 更新已有项目的这三项参数。
- 在顶栏停止运行中的项目，或点击五个阶段查看日志与耗时。新建转画幅副本后可直接编辑、导出。所有分镜使用新编号，原项目的文件与缓存独立保留。
- 完成后打开「发布文案」复制标题、简介、标签、逐幕旁白和来源。文案文件为 `output/publish_kit.md`。升级前的成片可通过「重渲染」生成文案。
- 外部 Agent 可使用 `attach_image` 导入图片、`clone_project` 转画幅、`cancel_project` 中止运行中的后端任务。上传返回的 `asset_id` 可直接填入封面或图片卡的 `image_asset`。

## CLI 与验收

PowerShell 先设置 `$env:MOCK_LLM='true'`，macOS/Linux 执行 `export MOCK_LLM=true`。在 backend 目录运行：

```sh
ruff check app ../tests
pytest ../tests -v
python -m app.cli demo --topic "2026上海租房避坑"
python -m app.cli demo --topic "上海租房" --target-format video_9_16 --theme clean_light
python -m app.cli demo --topic "上海租房" --target-format cards_3_4 --theme warm_amber
python -m app.cli rebuild <项目ID>
```

在 frontend 目录运行 `npm run build`，静态产物在 `dist/`。测试强制使用独立临时数据库和 Mock 模式，媒体测试实际启动浏览器与 FFmpeg。

## 真实采编

在根目录 `.env` 设置 `MOCK_LLM=false`，配置 `LLM_BASE_URL`、`LLM_MODEL` 与 `LLM_API_KEY` 后重启服务。配置可选的 `TAVILY_API_KEY` 可启用 Tavily 检索，留空时使用 DuckDuckGo 与网页正文，三个文本节点共享 OpenAI 兼容客户端。edge-tts 配音需要网络；画面、字幕烧录和剪辑在本机执行。可按供应商费率设置 `INPUT_CNY_PER_MILLION` 与 `OUTPUT_CNY_PER_MILLION`（元/百万 token），默认费率为零。不要用真实模式运行验收或联调。


## 分镜接口

以下路径均相对于 `/api/projects/{id}`。分镜编辑支持待分镜审批或已完成的项目。封面固定为首幕，调序一次提交全量 ID。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/scenes` | 提交一个含模板、视觉字段、旁白与来源编号的新分镜 |
| PATCH / DELETE | `/scenes/{sid}` | 保存字段修改或移除分镜 |
| PUT | `/scenes/reorder` | 按 `{"scene_ids":[...]}` 排列 |
| POST | `/scenes/{sid}/preview` | 以未保存的视觉字段生成 PNG |
| GET | `/scenes/{sid}/thumbnail` | 加载当前分镜缩略图 |
| POST | `/scenes/{sid}/rewrite` | 传入 `intent` 和可选 `narration`，获取润色草稿 |
| POST | `/scenes/{sid}/audition` | 传入 `narration`，试听 MP3 |

项目可选 `brand_label` 设置署名，`transition` 支持 `fade` 和 `slideleft`。缓存计入主题、画幅、声音、署名、转场、模板与版面页码。真实配音从 edge-tts 词边界生成 ASS 字幕；离线演示使用普通话合成和按段落分配的模拟时间轴。两种模式都在本地执行响度处理、字幕烧录和转场合成。

## 双模式使用指南

在「新建项目 → 执行模式」选择推理来源。浏览器可用 API Key 或本地 Agent CLI 自动完成采编、核查、导演与单幕润色。也可以选择 MCP，让当前对话中的 Agent 自己供稿。执行模式按项目保存，旧项目自动使用 API。

| 选择 | 根目录 `.env` 配置 | 工作台行为 |
| --- | --- | --- |
| API Key 模式 | `MOCK_LLM=false`，设置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` | 创建后启动流水线，可手动审批 |
| 本地 Agent 额度（CLI） | `MOCK_LLM=false`，设置 `AGENT_CLI_PRESET=codex` 或 `claude` | 后端启动已登录的本机 CLI，用 stdin 提交材料并读取 JSON |
| 外部 Agent 协同（MCP） | 在 Agent 客户端注册下方 stdio 服务 | 创建空项目，外部写入的资料、分镜和渲染进度通过 SSE 更新工作台 |

`DEFAULT_EXECUTION_MODE=agent_cli` 将网页默认选项切到本地额度。请先在启动后端的同一账户下安装并登录 CLI。引擎探测检查命令是否存在，登录状态由 CLI 在调用时确认。额度与账单归属取决于该 CLI 的认证配置。自定义程序使用 `AGENT_CLI_PRESET=custom` 和 `AGENT_CLI_CMD='/绝对路径/程序 参数'`，从 stdin 读取整段 UTF-8 提示，在 stdout 输出 JSON 对象。默认超时为 180 秒，可通过 `AGENT_CLI_TIMEOUT` 调整。修改配置后重启后端。离线验收设置 `MOCK_LLM=true`，优先使用内置采编材料、推理结果和离线语音。

### 接入 Codex、Claude Code 或 Cursor

完成上方本地安装后，在项目根目录执行其中一条命令。客户端会自行启动 MCP 子进程。

```sh
# Codex
codex mcp add reelforge -- "$PWD/.venv/bin/python" -m app.mcp_server

# Claude Code
claude mcp add --transport stdio reelforge -- "$PWD/.venv/bin/python" -m app.mcp_server
```

Codex 也可从工作台「连接外部 Agent（MCP）」复制 TOML 至 `~/.codex/config.toml`。Claude Code 项目配置文件为 `.mcp.json`，Cursor 为 `.cursor/mcp.json`。以下示例的 command 应替换为本地虚拟环境的绝对路径。

```json
{
  "mcpServers": {
    "reelforge": {
      "command": "/Users/ryan/Documents/tools/ReelForge/.venv/bin/python",
      "args": ["-m", "app.mcp_server"]
    }
  }
}
```

网页服务运行时，工具默认访问 `http://127.0.0.1:8000`，可用 `REELFORGE_API_BASE` 指定地址。服务未启动时，工具在 MCP 进程内调用同一套 API、SQLite 和渲染器。无头导出视频时，启动客户端的环境需要能找到 `ffmpeg` 与 `ffprobe`。

### 在 Agent 对话中制作和局部重渲染

1. **创建**　发送「请用 ReelForge 创建横屏项目《中文资料核对》，返回工作台链接」。Agent 调用 `create_project`。已有项目可直接从工作台复制带项目 ID 的协作指令。
2. **供稿**　发送「先查原始资料，保存来源链接、大纲、事实和数据，再根据分镜规范写入分镜，等我确认」。Agent 依次使用 `save_research`、`get_storyboard_schema`、`set_storyboard`。首幕为唯一封面，每幕引用已保存的来源编号。
3. **导出**　发送「分镜确认，渲染并告诉我文件路径与时长」。`render_project` 等待导出，返回分辨率、时长（毫秒）、绝对路径与缓存统计。
4. **改一幕**　发送「只缩短第二幕旁白，保留其他幕并重新导出」。Agent 从 `get_project_status` 获取幕 ID，调用 `update_scene` 和 `rebuild_project`。也可通过 `add_scene`、`delete_scene`、`reorder_scenes` 调整编排。幕数或页码变化会影响卡面缓存。
