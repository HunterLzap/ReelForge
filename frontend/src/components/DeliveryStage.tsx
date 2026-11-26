import { useState } from "react";
import { Download, FileJson, MonitorPlay } from "lucide-react";
import { resourceUrl } from "@/api/client";
import { useStudio } from "@/store/studioStore";
import { endOf, timecode } from "@/studio";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { StorageCard } from "./StudioControls";
export function DeliveryStage() {
  const {
    timeline: doc,
    delivery,
    exportTimeline,
    busy,
    project,
  } = useStudio();
  const [loaded, ready] = useState(false);
  if (!doc) return null;
  const result = delivery.result,
    url = resourceUrl(
      "/workspace/" +
        doc.project_id +
        "/output/final.mp4?v=" +
        doc.revision +
        (result ? "&export=" + result.revision : ""),
    );
  function json() {
    const href = URL.createObjectURL(
      new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = href;
    a.download = "timeline.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  }
  return (
    <main className="stage-page">
      <div className="page-title">
        <div>
          <p className="muted">导出交付</p>
          <h1>成片预览</h1>
        </div>
        <Button
          variant="primary"
          disabled={busy || delivery.status === "rendering" || !endOf(doc)}
          onClick={exportTimeline}
        >
          <Download />
          导出 1080P 成片
        </Button>
      </div>
      <div className="plan-grid">
        <Card className="stack">
          <div className="final-stage">
            <video
              key={url}
              src={result || project?.status === "COMPLETED" ? url : undefined}
              controls
              preload="metadata"
              onLoadedMetadata={() => ready(true)}
              onError={() => ready(false)}
            />
            {!loaded && (
              <div className="final-empty">
                <MonitorPlay />
                <span>导出后可在此预览成片</span>
              </div>
            )}
          </div>
          <div className="row">
            {loaded ? (
              <a className="btn" href={url} download="final.mp4">
                <Download />
                下载 MP4
              </a>
            ) : (
              <Button disabled>
                <Download />
                下载 MP4
              </Button>
            )}
            <Button onClick={json}>
              <FileJson />
              下载 JSON
            </Button>
          </div>
        </Card>
        <div className="stack">
          <Card className="stack">
            <h2>交付规格</h2>
            <div role="status">
              {delivery.status === "rendering" ? (
                <>
                  <span>正在渲染与合成…</span>
                  <progress />
                </>
              ) : delivery.status === "error" ? (
                delivery.message
              ) : result ? (
                "已完成 · r" + result.revision
              ) : (
                "等待导出"
              )}
            </div>
            <div className="between">
              时间轴
              <time>
                {doc.resolution.width} × {doc.resolution.height}
              </time>
            </div>
            <div className="between">
              帧率 / 时长
              <time>
                {doc.fps} fps · {timecode(endOf(doc))}
              </time>
            </div>
            {result && (
              <p className="muted">
                ffprobe · {result.width} × {result.height} · {result.fps} fps ·{" "}
                {timecode(result.duration_ms)}
              </p>
            )}
          </Card>
          <Card>
            <StorageCard />
          </Card>
        </div>
      </div>
    </main>
  );
}
