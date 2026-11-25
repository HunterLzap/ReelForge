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
      {p.fact_check && (
        <div className="note">
          {p.fact_check.summary}
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
