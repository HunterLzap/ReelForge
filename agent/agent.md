# ReelForge 工程文档总索引（Agent Master Map）

> **文档治理铁律**：本仓库仅维护用户手册 [README.md](file:///Users/ryan/Documents/tools/ReelForge/README.md) 与 `agent/` 目录下的 **6 个固定核心文档**。严禁在开发过程中随意新建其他零散 `.md` 文件。每完成一个里程碑，必须同步更新 [roadmap.md](file:///Users/ryan/Documents/tools/ReelForge/agent/roadmap.md) 的状态看板与本文件的路径映射表，确保文档、进度与源码始终统一。

---

## 1. 文档导航（按需按块读取，禁止全量塞入上下文）

| 文档 | 职责边界 | 何时必读 |
|---|---|---|
| [agent/agent.md](file:///Users/ryan/Documents/tools/ReelForge/agent/agent.md) | 总入口、功能→文档→代码文件映射表、协作验收铁律 | 每次开启新任务或接手项目时 |
| [agent/architecture.md](file:///Users/ryan/Documents/tools/ReelForge/agent/architecture.md) | 系统分层架构、目录结构、`main` 迁移策略、`local_mac` vs `cloud_2c2g` 双部署规范 | 涉及后端框架、部署、存储清理、安全或并发限制时 |
| [agent/contracts.md](file:///Users/ryan/Documents/tools/ReelForge/agent/contracts.md) | `TimelineDocument` 5 轨模型、原子 Patch、词级文稿、`ReviewPin`、Skill 规范、REST/MCP 契约 | 改动数据模型、API、MCP 工具或时间轴同步逻辑时 |
| [agent/design.md](file:///Users/ryan/Documents/tools/ReelForge/agent/design.md) | 方案 A 浅色 Token、7 大成熟产品对标、零造轮子开源组件栈、4 区剪辑与 Magpie 界面线框 | 改动任何前端页面、样式、交互控件或快捷键时 |
| [agent/models_and_sourcing.md](file:///Users/ryan/Documents/tools/ReelForge/agent/models_and_sourcing.md) | 硬件自适应探测、2C2G 模型防爆护栏、国内镜像下载、录屏精剪、`Crawl4AI` 联网爬取 | 涉及模型管理、ASR、视觉识图、网页抓取或素材对齐时 |
| [agent/roadmap.md](file:///Users/ryan/Documents/tools/ReelForge/agent/roadmap.md) | M1→M4 顺序路线图、实时进度看板、各里程碑验收门禁、8 项工程风险预案 | 规划排期、拆解里程碑任务单、做阶段验收时 |

---

## 2. 功能 → 权威文档 → 代码文件路径指引

> 说明：标注 `[现有 v2.0]` 表示当前 `main` 分支已存在的文件；标注 `[规划 v3.0]` 表示将在 M1–M4 按里程碑新增或重构的目标路径。

| 核心功能模块 | 权威规范章节 | 后端关联文件 | 前端 / 动效关联文件 |
|---|---|---|---|
| **1. 项目管理、数据库与并发锁** | `architecture.md §2–3` | `[现有]` `backend/app/main.py`, `db/database.py`, `db/repository.py`, `api/projects.py` | `[现有 M1]` `frontend/src/components/HomeView.tsx`, `StudioView.tsx` |
| **2. 多轨时间轴与原子 Patch / Undo** | `contracts.md §1–2` | `[现有 M1]` `backend/app/schemas/timeline.py`, `services/timeline_engine.py`, `api/timelines.py` | `[现有 M1]` `frontend/src/components/TimelinePanel.tsx`, `InspectorPanel.tsx`, `store/studioStore.ts`, `store/optimistic.ts` |
| **3. 动态视频预览与分层导出** | `architecture.md §4.1`<br>`design.md §2` | `[现有 M1]` `backend/app/media/assembler.py`, `tts.py`, `worker.py`, `media/proxy.py`, `media/remotion_runner.py`, `media/limits.py` | `[现有 M1]` `motion/src/Root.tsx`, `motion/src/TimelinePlayer.tsx`, `motion/src/components/*`, `frontend/src/components/Composition.tsx`, `PlanStage.tsx`, `EditStage.tsx`, `DeliveryStage.tsx` |
| **4. 录屏精剪（ASR / 文本剪辑 / 极速字幕 / 标注）** | `contracts.md §3`<br>`models_and_sourcing.md §3` | `[规划 M2]` `schemas/transcript.py`, `services/asr_service.py`, `services/screen_editor.py`, `api/transcripts.py` | `[规划 M2]` `frontend/src/components/TranscriptPane.tsx`, `SubtitleTable.tsx`, `skills/screen-tutorial/*` |
| **5. 画面框选审片批注（ReviewPin）** | `contracts.md §4`<br>`design.md §4.2` | `[现有 M1]` `schemas/review_pin.py`, `services/pin_service.py`, `api/review_pins.py` | `[现有 M1]` `frontend/src/components/ReviewCanvas.tsx`, `LeftRail.tsx` |
| **6. 本机探测、模型下载与 Magpie 路由** | `models_and_sourcing.md §1–2`<br>`design.md §4.3` | `[现有]` `core/config.py`, `api/system.py`<br>`[规划 M2]` `services/model_manager.py`, `services/model_router.py`, `api/models.py` | `[规划 M2]` `frontend/src/components/ModelRouterModal.tsx` |
| **7. 本地素材体检与 `Crawl4AI` 联网补料** | `contracts.md §5`<br>`models_and_sourcing.md §4` | `[现有 M1]` `media/assets.py`, `api/assets.py`, `api/media.py`, `services/uploads.py`, `schemas/asset.py`, `tools/web_search.py`<br>`[规划 M3]` `services/asset_indexer.py`, `services/web_sourcing.py`, `api/library.py` | `[规划 M3]` `frontend/src/components/MaterialDrawer.tsx` |
| **8. AI 导演对话与编导 Skill 插件** | `contracts.md §6`<br>`models_and_sourcing.md §4` | `[现有 M1]` `agents/{researcher,fact_checker,director}.py`, `schemas/skill.py`, `services/skill_registry.py`, `api/skills.py`, `skills/motion-editorial/*`<br>`[规划 M3/M4]` `services/director_chat.py`, `services/chat_editor.py` | `[现有 M1]` `frontend/src/studio.ts`, `skills/motion-editorial/components/*`<br>`[规划 M4]` `frontend/src/components/AiChatPane.tsx` |
| **9. 外部 Agent 协同（MCP）** | `contracts.md §7` | `[现有 M1]` `backend/app/mcp_server.py`（v2 14 工具 + M1 6 工具）, `api/external.py`<br>`[规划 M4]` 扩展至全量 Pin / Skill / Crawl / RoughCut 工具 | `[现有 M1]` MCP 同步实时刷新 (`stream.py`)<br>`[规划 M2]` `ModelRouterModal.tsx` |
| **10. 方案 A 浅色工作台与开源组件栈** | `design.md §1–4` | — | `[现有 M1]` `frontend/src/App.tsx`, `style.css`, `components/ui/*`, `CommandPalette.tsx`, `StudioControls.tsx`, `editorPlayback.ts`（`shadcn/ui` + `react-resizable-panels` + `cmdk` + `wavesurfer.js` + `@dnd-kit` + `@remotion/player`） |
| **11. 2C2G40G 磁盘自动清理与访问鉴权** | `architecture.md §4` | `[现有 M1]` `services/storage_manager.py`, `services/uploads.py`, `media/limits.py`, `core/auth.py` | `[现有 M1]` `StudioControls.tsx` (`StoragePill`), `DeliveryStage.tsx` 配额清理面板与令牌登录弹窗 |
| **12. 自动化测试与视觉验收** | `roadmap.md §2–3` | `[现有 M1]` `tests/conftest.py`, `test_api.py`, `test_engines.py`, `test_media_engine.py`, `test_orchestrator_mock.py`, `test_schemas.py`, `test_v3_m1.py` | `[规划 M2–M4]` `test_v3_m2..m4.py` + `workspace/v3-acceptance/` Playwright 与 2C2G 压测 |

---

## 3. 协作与验收铁律

1. **Orchestrator（总指挥）与 Coding Agent（Codex）职责分离**：Orchestrator 负责依据 `agent/*.md` 拆解任务单、审核 `git diff`、亲自查看截图/成片验收；Codex 负责具体编码、单测、构建与导出验收样本。
2. **每步完工必须三态核验**：代码静态检查（`ruff check`）、自动化测试（`MOCK_LLM=true pytest` + `npm run build`）、真实产物目视/流式交互验证。
3. **里程碑回写**：任意里程碑交付并提交前，必须同步刷新 `agent/roadmap.md` 中的状态看板与本文件的 `[现有]` 路径标注。
