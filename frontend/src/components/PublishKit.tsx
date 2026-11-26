import { useEffect, useState } from "react";
export default function PublishKit({
  id,
  version,
}: {
  id: string;
  version: number;
}) {
  const [text, set] = useState(""),
    [status, report] = useState("");
  useEffect(() => {
    let live = true;
    fetch("/api/projects/" + id + "/publish-kit")
      .then(async (r) => {
        if (!r.ok) throw Error("尚无发布文案，请重新导出");
        return r.text();
      })
      .then((x) => {
        if (live) set(x);
      })
      .catch((e) => {
        if (live) report(e.message);
      });
    return () => {
      live = false;
    };
  }, [id, version]);
  return (
    <article className="publish">
      <header>
        <h2>发布文案</h2>
        <button
          disabled={!text}
          onClick={() =>
            navigator.clipboard
              .writeText(text)
              .then(() => report("已复制"))
              .catch(() => report("请选中后复制"))
          }
        >
          复制文案
        </button>
      </header>
      <small>{status}</small>
      <pre>{text}</pre>
    </article>
  );
}
