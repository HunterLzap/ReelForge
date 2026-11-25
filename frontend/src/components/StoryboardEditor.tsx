import { useState } from "react";
import { Detail, Act, Scene } from "../types";
const names: Record<string, string> = {
  cover: "封面",
  big_quote: "金句",
  bullet_list: "要点清单",
  stat_chart: "数据图表",
  compare_split: "双栏对比",
  timeline: "时间轴",
};
function Editor({ s, p, act }: { s: Scene; p: Detail; act: Act }) {
  const [editing, open] = useState(false),
    [text, setText] = useState(s.narration),
    [json, setJson] = useState(""),
    [kind, setKind] = useState(s.template_type),
    [error, setError] = useState("");
  const can = ["WAITING_STORYBOARD", "COMPLETED"].includes(p.status);
  async function save() {
    try {
      const payload = JSON.parse(json);
      if (
        await act("/scenes/" + s.id, "PATCH", {
          template_type: kind,
          narration: text,
          visual_payload: payload,
        })
      )
        open(false);
    } catch {
      setError("视觉数据需要有效的 JSON");
    }
  }
  return (
    <div className="scene">
      <header>
        <b>
          {String(s.order_index).padStart(2, "0")}　{names[s.template_type]}
        </b>
        {can && (
          <button
            onClick={() => {
              setText(s.narration);
              setJson(JSON.stringify(s.visual_payload, null, 2));
              setKind(s.template_type);
              setError("");
              open(!editing);
            }}
          >
            {editing ? "取消" : "编辑"}
          </button>
        )}
      </header>
      {editing && can ? (
        <>
          <label>
            模板
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(names)
                .filter(([k]) => (k === "cover") === (s.order_index === 1))
                .map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
            </select>
          </label>
          <label>
            旁白
            <textarea value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <label>
            视觉数据（JSON）
            <textarea
              rows={8}
              value={json}
              onChange={(e) => setJson(e.target.value)}
            />
          </label>
          <p role="alert">{error}</p>
          <button onClick={save}>保存分镜</button>
        </>
      ) : (
        <p>{s.narration}</p>
      )}
      <small>
        {s.render_status === "DIRTY" ? "待渲染" : "已渲染"} ·{" "}
        {s.source_ids.join(" / ")}
      </small>
    </div>
  );
}
export default function StoryboardEditor({ p, act }: { p: Detail; act: Act }) {
  if (!p.scenes.length) return null;
  return (
    <section className="panel">
      <header>
        <h2>分镜脚本</h2>
        <small>{p.scenes.length} 幕</small>
      </header>
      {p.scenes.map((s) => (
        <Editor key={s.id} {...{ s, p, act }} />
      ))}
      {p.status === "WAITING_STORYBOARD" && (
        <button className="primary" onClick={() => act("/approve")}>
          通过分镜并渲染
        </button>
      )}
      {p.status === "COMPLETED" && (
        <button
          disabled={!p.scenes.some((s) => s.render_status === "DIRTY")}
          onClick={() => act("/rebuild")}
        >
          重新渲染改动分镜
        </button>
      )}
    </section>
  );
}
