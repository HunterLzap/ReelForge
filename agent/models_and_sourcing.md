# ReelForge v3.0 硬件自适应模型路由、录屏精剪与联网爬取引擎

> 上级索引：[agent/agent.md](file:///Users/ryan/Documents/tools/ReelForge/agent/agent.md)

---

## 1. 硬件自适应探测与双环境模型策略（适配 2C2G 国内云服务器）

运行 `POST /api/system/probe` 后，后端同时检测 **CPU/总内存/可用磁盘/FFmpeg/Playwright/本地模型缓存/端口网关（Magpie `3425`、Ollama `11434`、LM Studio `1234`）/Agent CLI**，并自动切换推荐策略：

### 1.1 两种部署画像的模型路由差异（硬防爆规则）

| 能力插槽 | `local_mac`（本机 ≥ 8 GB 内存默认） | `cloud_2c2g`（2 核 2 GB 国内云服务器默认） |
|---|---|---|
| **保护红线** | 允许运行单个轻量本地 ASR / Ollama 模型 | **硬拦截 > 300 MB 本地模型下载与加载**，彻底防止 2 GB 内存 OOM 杀进程 |
| **ASR 语音转写** | `mlx-whisper-large-v3-turbo-q4` (~580MB) 或 `faster-whisper-medium` (~780MB) / `SenseVoiceSmall` (~240MB) | **零内存国内云端 API**：阿里云百炼 Paraformer / 硅基流动 SenseVoiceSmall API / 火山语音 / OpenAI 兼容 Whisper API |
| **LLM 编导与改稿** | 本机 Codex/Claude CLI、Magpie 网关、Ollama 或云端 API | **国内直连高速 API**：DeepSeek / 通义千问（百炼）/ 硅基流动 / 豆包等 OpenAI 兼容端点 |
| **VLM 画面识图** | 本地 `qwen2.5vl:3b`（Ollama）或云端多模态 API | 云端多模态 API（如 `qwen-vl-plus` / 豆包视觉），服务器零显存/内存开销 |
| **TTS 旁白配音** | `edge-tts`（在线自然语音）+ 离线兜底 | `edge-tts`（实测国内可用，耗时仅占几 MB 内存）+ 可选云端商用 TTS |

### 1.2 本机推荐轻量模型一键下载清单（`local_mac` 专用，默认国内镜像源）

设置中心默认优先走 **`ModelScope` / `HF-Mirror`**（可一键切回 HuggingFace 官方源），支持断点续传、SSE 实时进度条与取消：

| 模型名称 | 体积 | 峰值内存 | 用途 |
|---|---|---|---|
| `mlx-community/whisper-large-v3-turbo-q4` | ~580 MB | ~1.2 GB | Apple Silicon MLX 原生中文 ASR + 词级时间戳（首选） |
| `Systran/faster-whisper-medium` (int8) | ~780 MB | ~1.4 GB | 跨平台通用中文 ASR 备选 |
| `FunAudioLLM/SenseVoiceSmall` (ONNX) | ~240 MB | ~0.6 GB | 中英混杂极快口播识别 |
| `qwen2.5vl:3b` (Ollama) | ~2.4 GB | ~3.5 GB | 离线本地素材抽帧识图 |
| `reader-lm-v2` (1.5B, Ollama) | ~1.0 GB | ~1.8 GB | 离线复杂 HTML → 干净 Markdown 清洗小模型 |

---

## 2. 系统录屏与口播精剪引擎（`asr_service.py` + `screen_editor.py`）

1. **三段式精准粗剪（非盲删，生成可审阅删除建议清单）**：
   * **物理静音层**：FFmpeg `silencedetect` 扫描 `> 450ms` 且低于 `-38dB` 的空白停顿。
   * **词级口癖层**：利用 ASR 词级时间戳标出“嗯、啊、那个、就是说”等填充词。
   * **语义重说层**：LLM 比对相邻句语义，识别“口误后重新说了一遍同一句话”，建议删去前一句保留后一句。
   * **人工保护机制**：默认保留 `padding_ms = 80ms` 自然呼吸感，间隙 `< 220ms` 不硬切；文稿区任何被标记削除的文字点一下即可复原。
2. **极速字幕精校**：
   * 表格视图内点句秒跳帧，支持行内直接编辑、光标处回车拆成两条、快捷键 `Cmd+M` 合并相邻两句、超出单行安全长度标黄提醒。
   * **项目专有名词词表**：填一次如 `FastAPI`、`ReelForge` 即可全片一键批量纠错，并同步加入下次 ASR 热词提示词。
3. **重点标注与包装**：
   * 预览画布直接框选区域生成 `zoom_focus`（平滑放大 + 聚光灯暗化周边）或 `callout_box`（说明气泡），可拖调出现时段；导出时由 FFmpeg 裁剪缩放叠加。

---

## 3. AI 导演、本地素材体检与可插拔 AI 联网爬取（`web_sourcing.py`）

### 3.1 本地素材体检与语义对齐（`asset_indexer.py`）
* 基于文件大小 + mtime + SHA-256 增量索引，不重复扫描；视频经 `ffprobe` 读取规格并做 `scdet` 场景切分抽关键帧，交由 VLM 生成中文画面描述。
* 匹配分镜同时输出 **体检告警**：如 `横屏 16:9 强裁进 9:16 竖屏`、`素材时长 2.1s 短于本幕旁白 4.5s`、`画面过暗或无音轨`。

### 3.2 可插拔 AI 联网爬取与抓图架构（兼容 DeepSeek 及各类国内/海外接口）

采用 **「网页抓取器 + 结构化抽取模型」解耦插件层**，严格适配国内网络与 2C2G 低内存环境：

1. **本地大内存默认全能组合：`Crawl4AI` + OpenAI 兼容模型（DeepSeek / 通义千问 / Ollama）**
   * `Crawl4AI` 直接复用本地已安装的 Playwright Chromium（无需额外购买 SaaS 服务），执行 JS、清理 Cookie 弹窗，一次返回干净 Markdown、**评分过滤后的高清图片/视频 `result.media` 列表**，以及关键页面元素截图。
   * 结构化抽取层通过 `ModelRouter` 接入任意 OpenAI 兼容大模型（如 DeepSeek、通义千问、硅基流动或本机 Ollama），按分镜需求自动过滤广告图并提取准确图文出处；可选挂接 `ReaderLM-v2` 预处理降噪省 Token。
2. **2C2G 国内云服务器轻量极速组合（省内存、国内直连）**
   * **首选零浏览器 HTTP 链路**：`httpx` + `trafilatura` / 可选国内搜索（如博查 Bocha / Bing / Tavily）+ 公开 API 抽取（无需拉起 Chromium，内存占用 < 50 MB，响应毫秒级）。
   * **按需单实例抓图**：仅当用户明确要求“截取目标网页高清画面”或静态抽取缺少配图时，受 `BROWSER_CONCURRENCY=1` 互斥锁保护拉起单个 `Crawl4AI` / Playwright Chromium 页面，截完图后**立即关闭浏览器进程释放内存**（避免常驻占用 ~400 MB RAM）。
   * 可选插槽支持配置 `Firecrawl` / `Jina Reader` 云端抓取 API 以及 `Pexels` / `Pixabay` 免版权视频图库（国内服务器若网络受限设置 5 秒快失败兜底，不卡死主流程）。
3. **合规红线与快捷人工通道**
   * 明确**不**实现绕过登录墙、验证码或强反爬的封闭社媒爬虫；支持工作台 `Cmd+V` 剪贴板粘贴截图、拖拽上传与粘贴公开 URL 定向抓图。

### 3.3 缺料四态降级策略（永不卡死流程）
* 🟢 `aligned`：已匹配本地或联网选定素材；
* 🟡 `needs_fix`：比例或时长瑕疵（一键居中裁切 / 轻微慢放）；
* 🔵 `card_fallback`：无合适实拍时一键转为 `motion_card`（动态 HTML 信息卡）；
* ⬜ `placeholder`：保留缺料占位槽标明所需画面与时长，继续后续剪辑与配音试听。
