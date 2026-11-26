import { useState, FormEvent } from "react";
import { X } from "lucide-react";
import { formats } from "../types";
import { Engines, Mode } from "./EngineConnection";
export default function CreateProjectModal({
  engines,
  close,
  create,
}: {
  engines: Engines | null;
  close: () => void;
  create: (data: unknown) => Promise<void>;
}) {
  const available = !!engines?.available_clis.includes(engines.preset);
  const [mode, setMode] = useState<Mode>(
    available && engines?.default_execution_mode === "agent_cli"
      ? "agent_cli"
      : "api",
  );
  const [busy, setBusy] = useState(false);
  const [theme, selectTheme] = useState("editorial_dark");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    try {
      await create({
        ...Object.fromEntries(f),
        seed_only: f.has("seed_only"),
        auto_approve: f.has("auto_approve"),
      });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="overlay">
      <form role="dialog" aria-label="新建项目" onSubmit={submit}>
        <header>
          <h2>新建项目</h2>
          <button type="button" aria-label="关闭" onClick={close}>
            <X />
          </button>
        </header>
        <label>
          选题
          <input
            name="topic"
            required
            maxLength={240}
            autoFocus
            placeholder="例如：2026上海租房避坑"
          />
        </label>
        <label>
          执行模式
          <select
            name="execution_mode"
            value={mode}
            onChange={(e) => setMode(e.target.value as Mode)}
          >
            <option value="api">API Key 模式</option>
            <option value="agent_cli" disabled={!available}>
              本地 Agent 额度（CLI）
            </option>
            <option value="mcp">外部 Agent 协同（MCP）</option>
          </select>
        </label>
        {mode === "api" && (
          <small>
            {engines?.model} ·{" "}
            {engines?.api_configured ? "Key 已配置" : "Key 未配置"}
          </small>
        )}
        <p>
          <small>
            {engines?.mock_llm && "离线模拟已开启。"}本机 CLI ·{" "}
            {engines?.available_clis.join("、") || "未检测到"}。
            {!available && "请安装所选 CLI 或修改 AGENT_CLI_PRESET。"}
          </small>
        </p>
        <label>
          导出规格
          <select name="target_format">
            {Object.entries(formats).map(([k, v]) => (
              <option value={k} key={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          视觉主题
          <select
            name="theme"
            value={theme}
            onChange={(e) => selectTheme(e.target.value)}
          >
            <option value="editorial_dark">黑金杂志</option>
            <option value="clean_light">瑞士暖白</option>
            <option value="warm_amber">复古暖棕</option>
          </select>
        </label>
        <details>
          <summary>高级选项</summary>
          <label>
            频道署名
            <input name="brand_label" maxLength={32} placeholder="留空隐藏" />
          </label>
          <label>
            幕间转场
            <select name="transition">
              <option value="fade">叠化</option>
              <option value="wipeleft">向左擦除</option>
              <option value="slideup">向上推移</option>
              <option value="smoothleft">平滑左移</option>
              <option value="none">无转场</option>
            </select>
          </label>
          <label>
            配音
            <input name="voice" placeholder="使用默认中文女声" />
          </label>
          <label className="check">
            <input type="checkbox" name="auto_approve" />
            自动通过大纲与分镜审批
          </label>
          <label>
            语速
            <select name="speech_rate" defaultValue="+0%">
              {["-10%", "+0%", "+10%", "+20%"].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <label>
            字幕样式
            <select name="subtitle_style">
              <option value="pill_dark">深色胶囊</option>
              <option value="clean_stroke">清晰描边</option>
              <option value="highlight_bar">高亮色条</option>
            </select>
          </label>
          <label>
            参考资料
            <textarea
              name="seed_materials"
              placeholder="粘贴笔记或来源 URL"
              rows={3}
            />
          </label>
          <label className="check">
            <input type="checkbox" name="seed_only" />
            仅使用自带资料
          </label>
        </details>
        <button className="primary" disabled={busy}>
          {mode === "mcp" ? "创建协作项目" : "创建并启动"}
        </button>
      </form>
    </div>
  );
}
