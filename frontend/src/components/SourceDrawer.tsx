import { Detail } from "../types";
export default function SourceDrawer({
  p,
  close,
}: {
  p: Detail;
  close: () => void;
}) {
  return (
    <div className="overlay drawer">
      <aside role="dialog" aria-label="资料溯源">
        <header>
          <h2>资料溯源</h2>
          <button onClick={close}>关闭</button>
        </header>
        {p.sources.map((s) => (
          <article key={s.id}>
            <small>
              {s.id} · {s.credibility_note}
            </small>
            <h3>
              {s.url ? (
                <a target="_blank" rel="noreferrer" href={s.url}>
                  {s.title} ↗
                </a>
              ) : (
                s.title
              )}
            </h3>
            <p>{s.snippet}</p>
          </article>
        ))}
        {p.status === "COMPLETED" && (
          <a download href={"/workspace/" + p.id + "/output/sources.md"}>
            下载资料清单
          </a>
        )}
      </aside>
    </div>
  );
}
