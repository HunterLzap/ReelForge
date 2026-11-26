import { useRef, useState } from "react";
import {
  ArrowRight,
  Clapperboard,
  MessageSquare,
  Paperclip,
  Send,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useStudio, report, type Draft } from "@/store/studioStore";
import { aspects, clipName, timecode } from "@/studio";
import type { Shot, SourceState } from "@/types";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Select } from "./ui/select";
import { Field, Input } from "./ui/input";

const stateLabel: Record<SourceState, string> = {
  local_matched: "本地命中",
  web_fetched: "联网获取",
  motion_generated: "动效生成",
  placeholder: "待补全占位",
};
const starters = ["AI 模型新闻快报", "产品功能发布混剪", "知识科普拆解"];

export function PlanStage() {
  const {
    project,
    timeline: doc,
    skills,
    draft,
    setDraft,
    setStage,
    upload,
    acceptTimeline,
    refreshMedia,
    select,
    setRailTab,
  } = useStudio();
  const [prompt, setPrompt] = useState(""),
    [busy, setBusy] = useState(""),
    [web, setWeb] = useState(true);
  const file = useRef<HTMLInputElement>(null),
    replacing = useRef<string>("");
  if (!project || !doc) return null;
  const pid = project.id;
  const plan: Draft = draft || {
    shots: [],
    history: [],
    skill_id: doc.skill_id || "ai-news-montage",
    aspect_ratio: doc.aspect_ratio,
  };
  function updateShot(id: string, fields: Partial<Shot>) {
    const latest = useStudio.getState().draft;
    if (latest)
      setDraft(pid, {
        ...latest,
        shots: latest.shots.map((s) => (s.id === id ? { ...s, ...fields } : s)),
      });
  }
  async function send(message: string) {
    if (!message.trim() || busy) return;
    setBusy("正在编排分镜…");
    try {
      const r = await api.directorChat(pid, {
        skill_id: plan.skill_id,
        aspect_ratio: plan.aspect_ratio,
        message,
        history: plan.history,
        web_enabled: web,
      });
      setDraft(pid, {
        ...plan,
        base_revision: r.base_revision,
        shots: r.shots,
        history: [
          ...plan.history,
          { role: "user", content: message },
          { role: "assistant", content: r.reply },
        ].slice(-50) as Draft["history"],
      });
      setPrompt("");
      await refreshMedia(pid);
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
    }
  }
  async function apply() {
    if (!plan.shots.length || busy) return;
    setBusy("正在生成时间轴与旁白…");
    try {
      const timeline = await api.directorPlan(pid, { ...plan });
      if (useStudio.getState().project?.id !== pid) return;
      acceptTimeline(timeline);
      setDraft(pid, { ...plan, base_revision: timeline.revision });
      setStage("edit");
      toast.success("已应用导演分镜，可撤销此修订");
      await refreshMedia(pid);
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
    }
  }
  return (
    <main className="stage-page">
      <div className="page-title">
        <div>
          <p className="muted">策划与素材</p>
          <h1>{project.topic}</h1>
        </div>
        <Button onClick={() => setStage("edit")}>
          进入精剪 <ArrowRight />
        </Button>
      </div>
      <div className="plan-grid director-grid">
        <Card className="stack">
          <h2>
            <MessageSquare /> AI 导演对话
          </h2>
          <div className="director-controls">
            <Select
              label="编导 Skill"
              value={plan.skill_id}
              options={skills.map((s) => ({ value: s.id, label: s.name }))}
              onChange={(skill_id) => setDraft(pid, { ...plan, skill_id })}
            />
            <Select
              label="分镜画幅"
              value={plan.aspect_ratio}
              options={[...new Set([...aspects, plan.aspect_ratio])]}
              onChange={(aspect_ratio) =>
                setDraft(pid, { ...plan, aspect_ratio })
              }
            />
            <label>
              <input
                type="checkbox"
                checked={web}
                onChange={(e) => setWeb(e.target.checked)}
              />{" "}
              联网补料
            </label>
          </div>
          {plan.history.length > 0 && (
            <div className="chat-transcript" role="log">
              {plan.history.map((turn, i) => (
                <div className={"chat-turn " + turn.role} key={i}>
                  <small>{turn.role === "user" ? "你" : "AI 导演"}</small>
                  <p>{turn.content}</p>
                </div>
              ))}
            </div>
          )}
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              void send(prompt || project.topic);
            }}
          >
            <Field label="创作简报">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={
                  plan.history.length
                    ? "继续调整镜头、节奏或素材要求…"
                    : project.topic
                }
                rows={4}
              />
            </Field>
            <div className="topic-chips">
              {starters.map((s) => (
                <button
                  type="button"
                  disabled={!!busy}
                  key={s}
                  onClick={() => setPrompt(s)}
                >
                  {s}
                </button>
              ))}
            </div>
            <Button type="submit" disabled={!!busy}>
              <Send /> {busy || "发送简报"}
            </Button>
          </form>
        </Card>
        <Card className="stack">
          <div className="between">
            <h2>
              <Clapperboard /> 结构化分镜脚本表
            </h2>
            <div className="topic-chips">
              <small>{plan.shots.length || doc.tracks.video.length} 幕</small>{" "}
              <Button
                variant="primary"
                disabled={!plan.shots.length || !!busy}
                onClick={apply}
              >
                生成多轨时间轴 <ArrowRight />
              </Button>
            </div>
          </div>
          {plan.shots.length === 0 ? (
            <>
              {doc.tracks.video.length === 0 ? (
                <p className="empty">发送创作简报后，在这里核对分镜与素材。</p>
              ) : (
                doc.tracks.video.map((c) => (
                  <button
                    key={c.id}
                    className="shotline"
                    onClick={() => {
                      select({ track: "video", id: c.id });
                      if (c.kind === "placeholder") setRailTab("media");
                      setStage("edit");
                    }}
                  >
                    <span>{clipName(c)}</span>
                    {c.kind === "placeholder" && <small>补图</small>}
                    <time>{timecode(c.end_ms - c.start_ms)}</time>
                  </button>
                ))
              )}
            </>
          ) : (
            plan.shots.map((s, i) => (
              <section className="shot-edit" key={s.id}>
                <div className="between">
                  <strong>
                    {i + 1}. {s.title}
                  </strong>
                  <span className={"source-pill " + s.source_state}>
                    {stateLabel[s.source_state]}
                  </span>
                </div>
                <Field label="旁白">
                  <textarea
                    rows={2}
                    value={s.narration}
                    onChange={(e) =>
                      updateShot(s.id, { narration: e.target.value })
                    }
                  />
                </Field>
                <div className="shot-fields">
                  <Field label="画面检索">
                    <Input
                      value={s.visual_query}
                      onChange={(e) =>
                        updateShot(s.id, { visual_query: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="时长（秒）">
                    <Input
                      type="number"
                      min=".1"
                      max="120"
                      step=".1"
                      value={s.duration_ms / 1000}
                      onChange={(e) =>
                        updateShot(s.id, {
                          duration_ms: Math.round(
                            Number(e.target.value) * 1000,
                          ),
                        })
                      }
                    />
                  </Field>
                </div>
                {s.source_state === "placeholder" && (
                  <small>{s.placeholder_hint}</small>
                )}
                <Button
                  variant="ghost"
                  disabled={!!busy}
                  onClick={() => {
                    replacing.current = s.id;
                    file.current?.click();
                  }}
                >
                  <Paperclip />
                  补图 / 替换素材
                </Button>
              </section>
            ))
          )}
          <input
            hidden
            type="file"
            ref={file}
            accept="image/png,image/jpeg,image/webp,video/mp4,video/webm,video/quicktime"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              const id = replacing.current;
              setBusy("正在上传素材…");
              try {
                const a = await upload(f);
                if (a)
                  updateShot(id, {
                    asset_id: a.id,
                    source_state: "local_matched",
                    source_url: null,
                    placeholder_hint: null,
                  });
              } finally {
                setBusy("");
              }
            }}
          />
        </Card>
      </div>
    </main>
  );
}
