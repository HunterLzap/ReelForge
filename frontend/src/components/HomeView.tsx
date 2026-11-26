import { useEffect, useState } from "react";
import { Thumbnail } from "@remotion/player";
import {
  Clapperboard,
  Plus,
  ArrowUpRight,
  Trash2,
  Film,
  Clock3,
  Folder,
  MousePointer2,
  ScanLine,
  PanelsTopLeft,
  AudioLines,
  FileVideo,
} from "lucide-react";
import { api } from "@/api/client";
import { report, useStudio } from "@/store/studioStore";
import {
  modes,
  modeFor,
  aspects,
  headlineKey,
  timecode,
  endOf,
  assetClip,
  makeCard,
} from "@/studio";
import type { Aspect, Project, TimelineDocument } from "@/types";
import { StoragePill, CommandButton } from "./StudioControls";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";
import { Field, Input } from "./ui/input";
import { Dialog } from "./ui/dialog";
import { Select } from "./ui/select";
import { useComposition } from "./Composition";
export const stageNames = {
  plan: "① 策划对齐",
  edit: "② 精剪审片",
  delivery: "③ 导出交付",
};
function Poster({ doc }: { doc: TimelineDocument }) {
  const props = useComposition(doc);
  return (
    <div className="poster" aria-hidden>
      <Thumbnail
        {...props}
        frameToDisplay={Math.min(props.durationInFrames - 1, doc.fps)}
        style={{ width: "100%", height: "100%", pointerEvents: "none" }}
      />
    </div>
  );
}
function ProjectCard({ p, remove }: { p: Project; remove: () => void }) {
  const [doc, show] = useState<TimelineDocument | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .timeline(p.id)
      .then((d) => {
        if (alive) show(d);
      })
      .catch(report);
    return () => {
      alive = false;
    };
  }, [p.id, p.timeline_revision]);
  return (
    <Card className="project-card">
      <button
        className="project-open"
        onClick={() => useStudio.getState().open(p)}
      >
        <div className="project-art">
          {doc && endOf(doc) > 0 ? <Poster doc={doc} /> : <Film size={36} />}
          <Badge>{doc?.aspect_ratio ?? p.aspect_ratio ?? "16:9"}</Badge>
        </div>
        <div className="project-copy">
          <div className="muted">{modeFor(p.skill_id).short}</div>
          <h3>{p.topic}</h3>
          <div className="project-meta">
            <span>
              <Film />
              {doc?.tracks.video.length ?? "…"} 个镜头
            </span>
            <span>
              <Clock3 />
              {doc ? timecode(endOf(doc)) : "…"}
            </span>
            <span>r{doc?.revision ?? "…"}</span>
          </div>
        </div>
      </button>
      <Button
        className="delete-project"
        variant="ghost"
        aria-label={"删除 " + p.topic}
        onClick={remove}
      >
        <Trash2 size={15} />
      </Button>
    </Card>
  );
}
export function HomeView({
  create,
  palette,
}: {
  create: (id: string) => void;
  palette: () => void;
}) {
  const { projects, refreshHome } = useStudio();
  const [deleting, remove] = useState<Project | null>(null),
    [busy, setBusy] = useState(false);
  return (
    <>
      <header className="home-header">
        <div className="brand">
          <span className="brand-icon">
            <Clapperboard />
          </span>
          ReelForge <Badge>v3.0</Badge>
        </div>
        <div className="row">
          <Button onClick={() => useStudio.getState().showModels("models")}>
            模型
          </Button>
          <StoragePill />
          <CommandButton open={palette} />
          <Button variant="primary" onClick={() => create("motion-editorial")}>
            <Plus />
            新建作品
          </Button>
        </div>
      </header>
      <main className="home">
        <h1>创作工作区</h1>
        <p className="intro">从一种创作模式开始，或继续剪辑最近的作品。</p>
        <div className="mode-grid">
          {modes.map((m, i) => (
            <button
              key={m.id}
              onClick={() => create(m.id)}
              className={"mode mode-" + i}
            >
              <div className="mode-art" aria-hidden>
                {i === 0 ? (
                  <div className="mini-screen">
                    <div className="mini-window">
                      <PanelsTopLeft />
                      <i />
                      <i />
                    </div>
                    <MousePointer2 />
                  </div>
                ) : i === 1 ? (
                  <div className="mini-film">
                    <span>
                      <Film />
                    </span>
                    <span>
                      <AudioLines />
                    </span>
                    <span>
                      <ScanLine />
                    </span>
                  </div>
                ) : (
                  <div className="mini-cards">
                    <i />
                    <i />
                    <strong>Aa</strong>
                  </div>
                )}
              </div>
              <div className="mode-copy">
                <h2>
                  {m.name}
                  <ArrowUpRight size={18} />
                </h2>
                <p>{m.caption}</p>
              </div>
            </button>
          ))}
        </div>
        <div className="section-title">
          <h2>
            <Folder />
            最近作品
          </h2>
          <span>{projects.length} 个作品</span>
        </div>
        <div className="project-grid">
          {projects.map((p) => (
            <ProjectCard key={p.id} p={p} remove={() => remove(p)} />
          ))}
        </div>
        {!projects.length && (
          <div className="empty">还没有作品，选择上方模式创建第一个作品。</div>
        )}
      </main>
      <Dialog
        open={!!deleting}
        onOpenChange={(v) => {
          if (!v && !busy) remove(null);
        }}
        title="删除作品"
      >
        <p>将删除《{deleting?.topic}》及其素材、修订和导出文件。</p>
        <div className="actions">
          <Button onClick={() => remove(null)}>取消</Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={async () => {
              if (!deleting) return;
              setBusy(true);
              try {
                await api.remove(deleting.id);
                remove(null);
                await refreshHome();
              } catch (e) {
                report(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            确认删除
          </Button>
        </div>
      </Dialog>
    </>
  );
}
export function CreateDialog({
  mode,
  close,
}: {
  mode: string;
  close: () => void;
}) {
  const [topic, title] = useState(""),
    [aspect, ratio] = useState<Aspect>(
      mode === "ai-news-montage" ? "9:16" : "16:9",
    ),
    [template, choose] = useState("none"),
    [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false);
  const skills = useStudio((s) => s.skills),
    templates =
      skills.find((s) => s.id === "motion-editorial")?.templates ?? [];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !topic.trim()) return;
    setBusy(true);
    try {
      const p = await api.create(topic.trim(), mode, aspect, "");
      await useStudio.getState().open(p);
      const s = useStudio.getState();
      if (s.project?.id !== p.id || !s.timeline) return;
      const ops = [];
      if (template !== "none") {
        const card = makeCard(0, topic);
        card.component_id = template;
        card.props = {
          tag: modeFor(mode).short,
          [headlineKey(template)]: topic,
        };
        ops.push({
          op: "add_clip" as const,
          track: "video" as const,
          clip: card,
        });
      }
      if (file) {
        const asset = await s.upload(file);
        if (asset) {
          const item = assetClip(asset, s.timeline);
          if (ops.length && item.track === "video") {
            item.clip.start_ms += 3000;
            item.clip.end_ms += 3000;
          }
          ops.push({ op: "add_clip" as const, ...item });
        }
      }
      if (ops.length) await s.patchTimeline(ops, "添加起始素材");
      close();
      void s.refreshHome().catch(report);
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(v) => {
        if (!v && !busy) close();
      }}
      title={"新建" + modeFor(mode).short + "作品"}
    >
      <form className="stack" onSubmit={submit}>
        <Field label="作品标题">
          <Input
            autoFocus
            required
            maxLength={240}
            placeholder="为作品起个名字"
            value={topic}
            onChange={(e) => title(e.target.value)}
          />
        </Field>
        <Field label="画幅">
          <Select
            label="作品画幅"
            options={aspects}
            value={aspect}
            onChange={ratio}
          />
        </Field>
        <Field label="起始模板（可选）">
          <Select
            label="起始模板"
            options={[
              { value: "none", label: "空白时间轴" },
              ...templates.map((t) => ({ value: t.id, label: t.name })),
            ]}
            value={template}
            onChange={choose}
          />
        </Field>
        <label className="file-label">
          <FileVideo />
          {file?.name ?? "选择起始素材（可选）"}
          <input
            type="file"
            accept=".mp4,.mov,.webm,.mp3,.wav,.m4a,.png,.jpg,.jpeg,.webp"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <div className="actions">
          <Button onClick={close} disabled={busy}>
            取消
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={!topic.trim() || busy}
          >
            {busy ? "正在创建…" : "创建作品"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
