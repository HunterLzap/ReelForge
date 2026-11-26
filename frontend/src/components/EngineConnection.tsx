import { useState } from "react";
export type Mode = "api" | "agent_cli" | "mcp";
export const labels = { api: "API", agent_cli: "Agent CLI", mcp: "MCP 协同" };
export interface Engines {
  mock_llm: boolean;
  api_configured: boolean;
  model: string;
  available_clis: string[];
  preset: string;
  default_execution_mode: Mode;
  mcp_config: {
    mcpServers: { reelforge: { command: string; args: string[] } };
  };
}
export function EngineConnection({
  id,
  engines,
  close,
}: {
  id: string;
  engines: Engines | null;
  close: () => void;
}) {
  const [target, setTarget] = useState("Codex");
  const [message, setMessage] = useState("");
  const server = engines?.mcp_config.mcpServers.reelforge;
  const config =
    server &&
    (target === "Codex"
      ? [
          "[mcp_servers.reelforge]",
          "command = " + JSON.stringify(server.command),
          "args = " + JSON.stringify(server.args),
        ].join("\n")
      : JSON.stringify(engines?.mcp_config, null, 2));
  const instruction =
    "请使用 ReelForge MCP 协作处理项目 " +
    id +
    "。先查看项目状态与分镜规范，再保存有出处的资料并写入分镜。我确认后再渲染成片。";
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setMessage("已复制");
    } catch {
      setMessage("请选中文本手动复制");
    }
  }
  return (
    <div className="overlay">
      <form role="dialog" aria-label="连接外部 Agent">
        <header>
          <h2>连接外部 Agent</h2>
          <button type="button" onClick={close}>
            关闭
          </button>
        </header>
        <label>
          客户端
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {["Codex", "Claude Code", "Cursor"].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label>
          {target === "Codex"
            ? "~/.codex/config.toml"
            : target === "Cursor"
              ? ".cursor/mcp.json"
              : ".mcp.json"}
          <textarea readOnly rows={6} value={config || ""} />
        </label>
        <button
          type="button"
          disabled={!config}
          onClick={() => config && copy(config)}
        >
          复制配置
        </button>
        <label>
          项目 ID <code>{id}</code>
        </label>
        <textarea readOnly rows={4} value={instruction} />
        <button type="button" onClick={() => copy(instruction)}>
          复制协作指令
        </button>
        <small role="status">{message}</small>
      </form>
    </div>
  );
}
