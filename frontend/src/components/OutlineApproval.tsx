import { Detail, Act } from "../types";
export default function OutlineApproval({ p, act }: { p: Detail; act: Act }) {
  if (!p.research) return null;
  return (
    <section className="panel">
      <h2>采编大纲</h2>
      <ol>
        {p.research.outline.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ol>
      {!!p.research.data_points?.length && <details><summary>数据与出处</summary>{p.research.data_points.map((point,i)=><p key={i}>{point.claim} · {point.source_ids.join(" / ")}</p>)}</details>}
      {p.fact_check && (
        <div className="note">
          {p.fact_check.summary}
          {!!p.fact_check.checks?.length && <details><summary>逐条核查记录</summary>{p.fact_check.checks.map((c,i)=><p key={i}>{c.claim} · {c.source} · {c.verdict==="supported"?"有依据":c.verdict}</p>)}</details>}
          {p.fact_check.issues.map((x, i) => (
            <p key={i}>{x}</p>
          ))}
        </div>
      )}
      {p.status === "WAITING_OUTLINE" && (
        <button className="primary" onClick={() => act("/approve")}>
          通过大纲，生成分镜
        </button>
      )}
    </section>
  );
}
