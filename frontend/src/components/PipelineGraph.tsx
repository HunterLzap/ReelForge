import {
  Search,
  ShieldCheck,
  Clapperboard,
  Layers,
  Film,
  Check,
} from "lucide-react";
import { Detail } from "../types";
const nodes = [
  [Search, "资料采编", "RESEARCHING"],
  [ShieldCheck, "事实核查", "FACT_CHECKING"],
  [Clapperboard, "分镜编排", "DIRECTING"],
  [Layers, "媒体渲染", "RENDERING"],
  [Film, "成片导出", "ASSEMBLING"],
] as const;
export default function PipelineGraph({ p }: { p: Detail }) {
  const status = p.status === "FAILED" ? p.logs.at(-1)?.stage_name : p.status;
  const index =
    status === "COMPLETED"
      ? 5
      : status === "WAITING_OUTLINE"
        ? 2
        : status === "WAITING_STORYBOARD"
          ? 3
          : nodes.findIndex((n) => n[2] === status);
  return (
    <section className="panel">
      <h2>生产流程</h2>
      <div className="nodes">
        {nodes.map(([Icon, label, k], i) => (
          <div
            key={k}
            className={i < index ? "done" : k === status ? "active" : ""}
          >
            {i < index ? <Check /> : <Icon />}
            <strong>{label}</strong>
          </div>
        ))}
      </div>
      <details>
        <summary>运行日志 · {p.logs.length}</summary>
        <ol className="logs">
          {p.logs.map((l) => (
            <li key={l.id}>
              <time>{l.created_at.slice(11)}</time>
              {l.message}
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
