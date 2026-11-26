import { useState } from "react";
import {
  Search,
  ShieldCheck,
  Clapperboard,
  Layers,
  Film,
  X,
} from "lucide-react";
import { Detail } from "../types";
const stages = [
  ["采编", "RESEARCHING", "Researcher", Search],
  ["核查", "FACT_CHECKING", "FactChecker", ShieldCheck],
  ["分镜", "DIRECTING", "Director", Clapperboard],
  ["渲染", "RENDERING", "RENDERING", Layers],
  ["导出", "ASSEMBLING", "ASSEMBLING", Film],
] as const;
function stageInfo(p: Detail, i: number) {
  const [, stage, agent] = stages[i],
    runs = p.stage_runs.filter((r) => r.stage_name === agent);
  const run = runs.at(-1);
  return {
    run,
    state:
      p.status === stage
        ? "运行中"
        : run?.summary === "任务已中止"
          ? "已中止"
          : run?.status === "FAILED"
            ? "失败"
            : run?.status === "OK"
              ? "完成"
              : "—",
  };
}
export default function PipelineGraph({
  p,
  open,
}: {
  p: Detail;
  open: () => void;
}) {
  return (
    <button
      className="pipeline"
      title="运行轨迹"
      aria-label="运行轨迹"
      onClick={open}
    >
      {stages.map(([name, , , Icon], i) => (
        <span key={name} data-state={stageInfo(p, i).state}>
          <Icon size={14} />
          <b>{name}</b>
        </span>
      ))}
    </button>
  );
}
export function Trace({ p, close }: { p: Detail; close: () => void }) {
  const [i, select] = useState(
    Math.max(
      0,
      stages.findIndex(([, s]) => s === p.status),
    ),
  );
  const [name, stage, agent] = stages[i];
  const logs = p.logs.filter(
    (l) =>
      l.stage_name === stage ||
      (i === 2 && ["EDITOR", "WAITING_STORYBOARD"].includes(l.stage_name)) ||
      (i === 1 && l.stage_name === "WAITING_OUTLINE") ||
      (i === 4 && l.stage_name === "COMPLETED") ||
      (l.stage_name === "CANCELLED" &&
        p.logs
          .slice(0, p.logs.indexOf(l))
          .reverse()
          .find((x) => stages.some((s) => s[1] === x.stage_name))
          ?.stage_name === stage),
  );
  return (
    <div className="overlay drawer">
      <aside role="dialog" aria-label="运行轨迹" className="trace">
        <header>
          <h2>运行轨迹</h2>
          <button onClick={close} aria-label="关闭">
            <X />
          </button>
        </header>
        <div className="trace-grid">
          <section>
            {stages.map(([n, , , Icon], j) => {
              const { run, state } = stageInfo(p, j);
              return (
                <button
                  key={n}
                  aria-pressed={i === j}
                  onClick={() => select(j)}
                >
                  <Icon size={15} />
                  <span>
                    {n}
                    <small>
                      {state} ·{" "}
                      {run ? (run.duration_ms / 1000).toFixed(1) + " s" : "—"}
                    </small>
                  </span>
                </button>
              );
            })}
          </section>
          <section>
            <h3>{name}日志</h3>
            {logs.map((l) => (
              <p key={l.id}>
                <time>{l.created_at.slice(11)}</time> {l.message}
              </p>
            ))}
            {p.stage_runs
              .filter((r) => r.stage_name === agent)
              .map((r, j) => (
                <p key={j}>{r.summary}</p>
              ))}
            {!logs.length && !stageInfo(p, i).run && <p>暂无记录</p>}
          </section>
        </div>
      </aside>
    </div>
  );
}
