# ReelForge（映铸）：全自动多媒体内容工厂架构与目标计划书

**ReelForge** 是一个本地优先、可观测、支持人机协同的 **Multi-Agent 多媒体内容生产工作台**。用户输入一个选题并选择目标平台规格（`16:9` 横屏视频 / `9:16` 竖屏短视频 / `3:4` 小红书图文卡），系统通过 5 个职责清晰的 Agent 接力完成「全网采编 → 事实核查 → 结构化分镜 → 零成本视觉与配音渲染 → 本地剪辑合成」，交付可直接发布的 **1080P MP4 成片**、**多图卡片包** 以及 **带原始 URL 溯源的资料清单**。

---

## 1. 核心架构原则与边界

1. **运行时零媒体 API 成本**：画面渲染、配音、字幕与视频剪辑全部在本地通过 `Playwright + edge-tts + FFmpeg` 完成，不引入付费生图、生视频或商业 TTS 服务。
2. **LLM 成本可控且可全量 Mock**：仅在 `Researcher`、`FactChecker`、`Director` 三个文本节点调用 OpenAI 兼容协议 LLM；统一经由 `LLMClient` 收口，内置 `MOCK_LLM=true` 模式，保证全部自动化测试与离线联调零 API 消耗。
3. **单幕级缓存与局部重渲染**：基于 SQLite 状态机与单幕 `content_hash`，修改任意一幕文案或模板后，仅重新渲染变更分镜并快速重新拼接，不重跑前置 LLM 节点。
4. **跨平台与确定性**：统一使用 `pathlib.Path` 兼容 Windows 与 macOS；视觉模板禁止外网 CDN（内联 CSS + 内联 SVG 图表）；FFmpeg 编码统一为 `libx264 (yuv420p) + aac`。

---

## 2. 本地技术栈与环境准备

### 2.1 系统级环境
* **Python 3.11+**（推荐使用 `uv` 管理虚拟环境与依赖）
* **Node.js 20 LTS**（用于前端 Vite + React 构建）
* **FFmpeg 6.0+**（需包含 `ffprobe`，并加入系统 `PATH`）
* **Playwright Chromium**：安装后端依赖后执行 `playwright install chromium`

### 2.2 后端技术栈（`backend/pyproject.toml`）
* **Web 与状态**：`fastapi`, `uvicorn[standard]`, `pydantic>=2.8`, `pydantic-settings`, `aiosqlite`
* **Agent 与检索**：`openai`（兼容 DeepSeek / 通义千问 / OpenAI / Ollama）, `httpx`, `duckduckgo-search`, `trafilatura`, `typer`
* **本地媒体引擎**：`jinja2`, `playwright`, `edge-tts`
* **测试与规范**：`pytest`, `pytest-asyncio`, `ruff`

### 2.3 前端技术栈（`frontend/`）
* **React 18 + TypeScript + Vite 5 + Tailwind CSS 3 + lucide-react**
* 使用原生 `fetch` + `EventSource`（SSE）与后端通信，保持轻量。

### 2.4 环境变量配置（`.env.example`）
```env
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
MOCK_LLM=false

MAX_SEARCH_RESULTS_PER_QUERY=4
MAX_FACT_CHECK_LOOPS=1
MAX_DIRECTOR_RETRIES=2
DEFAULT_TTS_VOICE=zh-CN-XiaoxiaoNeural
WORKSPACE_DIR=./workspace
DATABASE_PATH=./workspace/reelforge.db
```

---

## 3. 项目文件目录架构

```text
reelforge/
├── PROJECT_PLAN.md                  # 项目架构与目标计划书
├── .env.example                     # 环境变量模板
├── .gitignore                       # 忽略 .env, workspace/, __pycache__, node_modules, dist
├── README.md                        # 安装、启动与使用说明
├── assets/
│   ├── bgm/                         # 可选免版权背景音乐（目录为空时自动跳过混音）
│   └── fonts/                       # 可选本地 CJK 字体（为空时回退系统默认中文字体）
├── workspace/                       # 运行时产物隔离目录（自动创建）
│   ├── reelforge.db                 # SQLite 数据库
│   └── {project_id}/
│       ├── research.json            # 采编结果快照
│       ├── fact_check.json          # 核查报告快照
│       ├── storyboard.json          # 分镜脚本快照
│       ├── scenes/{scene_id}/       # card.html, card.png, audio.mp3, subs.srt, clip.mp4, meta.json
│       └── output/                  # final.mp4, cards/*.png, sources.md
├── backend/
│   ├── pyproject.toml
│   └── app/
│       ├── main.py                  # FastAPI 入口、静态文件挂载、生命周期初始化
│       ├── cli.py                   # CLI 入口（支持 mock/真实跑通与局部重跑）
│       ├── core/
│       │   ├── config.py            # 配置加载
│       │   ├── llm_client.py        # 统一 LLM 封装（JSON 模式、Token 统计、MOCK_LLM）
│       │   └── events.py            # 内存 SSE 事件总线
│       ├── db/
│       │   ├── database.py          # aiosqlite 初始化与建表
│       │   └── repository.py        # 数据访问层（CRUD 统一收口）
│       ├── schemas/
│       │   ├── project.py           # Project, FormatType, ProjectStatus
│       │   ├── research.py          # ResearchPack, SourceItem, FactCheckReport
│       │   ├── storyboard.py        # StoryboardScript, SceneItem, 6 种 visual_payload
│       │   └── pipeline.py          # StageRun, SSEEvent
│       ├── agents/
│       │   ├── base.py              # BaseAgent（统一耗时与 Token 统计）
│       │   ├── researcher.py        # 节点 1：拆子问题 → 搜索抓取 → 提炼素材包
│       │   ├── fact_checker.py      # 节点 2：交叉核验 → 决定放行或打回补查
│       │   └── director.py          # 节点 3：生成结构化分镜 JSON（含 Schema 校验重试）
│       ├── tools/
│       │   └── web_search.py        # DuckDuckGo 搜索 + trafilatura 正文抽取 + 超时兜底
│       ├── media/
│       │   ├── renderer.py          # 节点 4A：Jinja2 + Playwright 渲染 3 种画布尺寸
│       │   ├── tts.py               # 节点 4B：edge-tts 配音 + 字幕 SRT + ffprobe 时长
│       │   ├── assembler.py         # 节点 5：FFmpeg 单幕烧录字幕 + 无损拼接 + BGM 混音
│       │   └── hash_util.py         # 单幕 content_hash 计算（局部重渲染缓存判断）
│       ├── pipeline/
│       │   └── orchestrator.py      # DAG 状态机（执行、打回环、审批暂停、单幕重跑）
│       ├── templates/               # 6 套确定性 HTML/CSS 视觉模板（纯内联样式与 SVG）
│       │   ├── base.html
│       │   ├── cover.html           # 封面卡
│       │   ├── big_quote.html       # 大字金句卡
│       │   ├── bullet_list.html     # 要点清单卡
│       │   ├── stat_chart.html      # 数据柱状/条形图卡（纯内联 SVG）
│       │   ├── compare_split.html   # 双栏对比卡
│       │   └── timeline.html        # 步骤/时间轴卡
│       └── api/
│           ├── projects.py          # 项目 CRUD 与产物访问
│           ├── pipeline.py          # 启动、审批、单幕编辑与局部重跑
│           └── stream.py            # SSE 实时进度推送
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── types/index.ts
│       ├── api/client.ts
│       └── components/
│           ├── CreateProjectModal.tsx   # 新建任务弹窗（选题、规格、主题、审批开关）
│           ├── PipelineGraph.tsx        # 5 节点 DAG 进度条与实时日志
│           ├── OutlineApproval.tsx      # 大纲与核查结果确认面板
│           ├── StoryboardEditor.tsx     # 分镜列表、在线编辑与单幕局部重渲染
│           ├── PreviewStudio.tsx        # 视频播放器、图文画廊与导出下载
│           └── SourceDrawer.tsx         # 资料溯源抽屉
└── tests/
    ├── test_schemas.py
    ├── test_media_engine.py
    ├── test_orchestrator_mock.py
    └── test_api.py
```

---

## 4. 核心数据模型与接口契约

### 4.1 SQLite 核心表
* **`projects`**：`id`, `topic`, `target_format` (`video_16_9` | `video_9_16` | `cards_3_4`), `theme` (`editorial_dark` | `clean_light` | `warm_amber`), `voice`, `auto_approve`, `status`, `fact_check_loops`, `total_tokens`, `estimated_cost_cny`, `error_message`, `created_at`, `updated_at`。
* **`stage_runs`**：`id`, `project_id`, `stage_name`, `attempt`, `status`, `input_tokens`, `output_tokens`, `duration_ms`, `summary`, `created_at`。
* **`sources`**：`id`, `project_id`, `title`, `url`, `snippet`, `credibility_note`。
* **`scenes`**：`id`, `project_id`, `order_index`, `template_type`, `narration`, `visual_payload_json`, `source_ids_json`, `content_hash`, `duration_ms`, `render_status`。
* **`event_logs`**：`id`, `project_id`, `level`, `stage_name`, `message`, `created_at`。

### 4.2 6 套视觉模板 Payload 契约
由 Pydantic `Discriminated Union` 校验：
* `cover`：`title`, `subtitle`, `tag`（固定为第 1 幕）
* `big_quote`：`quote`, `highlight`, `attribution`
* `bullet_list`：`heading`, `items`（3–4 项：`label`, `desc`）
* `stat_chart`：`heading`, `unit`, `bars`（3–5 项：`label`, `value`, `accent`）, `takeaway`
* `compare_split`：`heading`, `left_title`, `left_points`, `right_title`, `right_points`
* `timeline`：`heading`, `steps`（3–4 项：`step_label`, `title`, `desc`）

### 4.3 三种画布规格
* `video_16_9`：`1920 × 1080` → 导出 `output/final.mp4` + `output/sources.md`
* `video_9_16`：`1080 × 1920` → 导出 `output/final.mp4` + `output/sources.md`
* `cards_3_4`：`1080 × 1440` → 导出 `output/cards/01.png ...` + `output/sources.md`（跳过配音与视频合成）

### 4.4 关键工程防坑设计
* **FFmpeg 字幕路径**：生成单幕 `clip.mp4` 时将子进程 `cwd` 设为 `scenes/{scene_id}`，传入相对文件名 `subs.srt`，避免 Windows 盘符冒号与反斜杠在 `subtitles` 滤镜中转义失败。
* **单幕局部重渲染**：计算 `sha256(target_format + theme + voice + template_type + narration + canonical_json(visual_payload))`，哈希未变且产物存在时直接复用缓存，仅重跑脏分镜并重新 `concat`。
* **DAG 状态流转**：`PENDING → RESEARCHING → FACT_CHECKING`（若关键事实无出处且 `fact_check_loops < 1` 则回退 `RESEARCHING`）`→ WAITING_OUTLINE`（`auto_approve=1` 时跳过）`→ DIRECTING → WAITING_STORYBOARD`（`auto_approve=1` 时跳过）`→ RENDERING → ASSEMBLING → COMPLETED`。

### 4.5 核心 API 端点
* `POST /api/projects` / `GET /api/projects` / `GET /api/projects/{id}`
* `POST /api/projects/{id}/run`（启动或恢复流水线）
* `POST /api/projects/{id}/approve`（大纲或分镜审批放行）
* `PATCH /api/projects/{id}/scenes/{scene_id}`（修改单幕并标为 `DIRTY`）
* `POST /api/projects/{id}/rebuild`（仅重渲染脏分镜并重合成成片）
* `GET /api/projects/{id}/stream`（SSE 实时事件流）
* 静态挂载 `/workspace/` 以支持前端在线播放 MP4 与下载卡片包。

---

## 5. 目标驱动执行路线图（Milestones）

### Milestone 1：核心骨架与本地出片闭环
* **目标**：搭好项目结构、数据库与 Schema、支持 `MOCK_LLM=true` 的 `LLMClient`、3 套基础视觉模板（`cover`, `bullet_list`, `big_quote`）、本地媒体引擎（Playwright + edge-tts + FFmpeg）以及 CLI 入口。
* **达成标志**：运行 `MOCK_LLM=true python -m app.cli demo --topic "测试选题"` 能端到端产出带中文画面、配音和字幕的可播放 `final.mp4`，且 `test_schemas.py` 与 `test_media_engine.py` 全部通过。

### Milestone 2：完整 5-Agent DAG 与多端视觉能力
* **目标**：实现真实网页检索（DuckDuckGo + trafilatura）、`Researcher` / `FactChecker` / `Director` 三个完整 Agent、剩余 3 套视觉模板（`stat_chart`, `compare_split`, `timeline`）、三种画布尺寸适配、`orchestrator.py` 状态机（含打回环与 `content_hash` 局部重渲染缓存）以及 `sources.md` 导出。
* **达成标志**：`test_orchestrator_mock.py` 覆盖正常全流程、Fact-Checker 打回重试、`cards_3_4` 图文直出、单幕修改缓存命中，`ruff check` 无报错。

### Milestone 3：FastAPI 服务端、SSE 与审批流
* **目标**：完成全部 REST API 路由、内存 SSE 事件总线、人工审批暂停/恢复流转（`WAITING_OUTLINE` / `WAITING_STORYBOARD`）以及成片后的局部重渲染接口。
* **达成标志**：`test_api.py` 集成测试全通过，FastAPI `/docs` 可正常访问。

### Milestone 4：React 前端工作台与全链路联调
* **目标**：完成 Vite + React + TypeScript 前端工作台（新建任务、5 节点实时进度条、大纲确认、分镜在线编辑与局部重渲染、MP4 预览与卡片画廊、资料溯源抽屉）与 `README.md` 启动文档。
* **达成标志**：`frontend` 执行 `npm run build` 零报错；全量 `pytest` 100% 通过；前后端联调可完整跑通一次任务创建到成片预览与单幕局部重渲染。
