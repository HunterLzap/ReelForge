import { ArrowRight, Plus, Film, Layers3 } from "lucide-react";
import { useStudio } from "@/store/studioStore";
import { clipName, makeCard, modeFor, timecode, endOf } from "@/studio";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { AspectControl } from "./StudioControls";
export function PlanStage() {
  const {
    timeline: doc,
    project,
    skills,
    patchTimeline,
    setStage,
    select,
  } = useStudio();
  if (!doc || !project) return null;
  const mode = modeFor(doc.skill_id),
    skill = skills.find((s) => s.id === doc.skill_id);
  return (
    <main className="stage-page">
      <div className="page-title">
        <div>
          <p className="muted">策划对齐</p>
          <h1>{project.topic}</h1>
        </div>
        <Button variant="primary" onClick={() => setStage("edit")}>
          进入 ② 精剪审片
          <ArrowRight />
        </Button>
      </div>
      <div className="plan-grid">
        <Card>
          <div className="heading">
            <h2>
              <Film />
              镜头概要
            </h2>
            <Badge>
              {doc.tracks.video.length} 个镜头 · {timecode(endOf(doc))}
            </Badge>
          </div>
          {doc.tracks.video.map((c, i) => (
            <button
              key={c.id}
              className="shotline"
              onClick={() => {
                select({ track: "video", id: c.id });
                setStage("edit");
              }}
            >
              <b>{String(i + 1).padStart(2, "0")}</b>
              <span>{clipName(c)}</span>
              <time>
                {timecode(c.start_ms)} – {timecode(c.end_ms)}
              </time>
            </button>
          ))}
          <Button
            className="add-shot"
            onClick={() =>
              patchTimeline(
                [
                  {
                    op: "add_clip",
                    track: "video",
                    clip: makeCard(
                      Math.max(0, ...doc.tracks.video.map((c) => c.end_ms)),
                      "新动效镜头",
                    ),
                  },
                ],
                "新增动效镜头",
              )
            }
          >
            <Plus />
            新增动效镜头
          </Button>
        </Card>
        <div className="stack">
          <Card className="stack">
            <h2>
              <Layers3 />
              创作模式
            </h2>
            <strong>{mode.name}</strong>
            <p className="muted">{skill?.description ?? mode.caption}</p>
          </Card>
          <Card className="stack">
            <h2>作品规格</h2>
            <div className="between">
              导出画幅
              <AspectControl />
            </div>
            <div className="between">
              帧率<time>{doc.fps} fps</time>
            </div>
            <div className="between">
              当前修订<Badge>r{doc.revision}</Badge>
            </div>
          </Card>
        </div>
      </div>
    </main>
  );
}
