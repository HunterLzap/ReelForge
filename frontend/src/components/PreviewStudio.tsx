import { Download } from "lucide-react";
import { Detail } from "../types";
export default function PreviewStudio({ p }: { p: Detail }) {
  if (p.status !== "COMPLETED") return null;
  const cards = p.target_format === "cards_3_4",
    base = "/workspace/" + p.id + "/output/",
    file = cards ? "cards.zip" : "final.mp4",
    v = "?v=" + p.logs.at(-1)?.id;
  return (
    <section className="panel">
      <header>
        <h2>成品预览</h2>
        <a download href={base + file + v}>
          <Download size={16} />
          下载{cards ? "卡片包" : "视频"}
        </a>
      </header>
      {cards ? (
        <div className="gallery">
          {p.scenes.map((s) => (
            <img
              alt={"第 " + s.order_index + " 幕"}
              key={s.id}
              src={
                base +
                "cards/" +
                String(s.order_index).padStart(2, "0") +
                ".png" +
                v
              }
            />
          ))}
        </div>
      ) : (
        <video key={v} controls preload="metadata" src={base + file + v} />
      )}
    </section>
  );
}
