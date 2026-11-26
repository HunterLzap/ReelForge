import { useState, useEffect } from "react";
import { SlidersHorizontal, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { usePlayback } from "./editorPlayback";
import { useStudio, report } from "@/store/studioStore";
import { api } from "@/api/client";
import { timecode, trackLabels, headlineKey, clipName } from "@/studio";
import type { Clip, TrackName, ReviewPin } from "@/types";
import type { CardProps } from "@motion/types";
import { Button } from "./ui/button";
import { Input, Field } from "./ui/input";
import { Select } from "./ui/select";
import { Switch } from "./ui/switch";
import { AspectControl } from "./StudioControls";
const styles = ["pill_dark", "highlight_bar", "clean_caption"];
function Edit({
  label,
  value,
  save,
  type = "text",
  min,
  max,
  step,
}: {
  label: string;
  value: string | number;
  save: (v: string) => void;
  type?: "text" | "number";
  min?: number;
  max?: number;
  step?: number;
}) {
  const [draft, set] = useState(String(value));
  useEffect(() => set(String(value)), [value]);
  return (
    <Field label={label}>
      <Input
        type={type}
        min={min}
        max={max}
        step={step ?? "any"}
        value={draft}
        onChange={(e) => set(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
        }}
        onBlur={(e) => {
          if (draft === String(value)) return;
          if (!e.target.validity.valid || (type === "number" && !draft)) {
            set(String(value));
            return;
          }
          save(draft);
          set(String(value));
        }}
      />
    </Field>
  );
}
function PinInspector({ pin: p }: { pin: ReviewPin }) {
  const { editPin, deletePin, timeline } = useStudio();
  return (
    <>
      <h3>审片批注 · {timecode(p.time_ms)}</h3>
      <img className="pin-frame" src={api.frame(p)} alt="批注所在帧" />
      <Edit
        label="批注内容"
        value={p.note}
        save={(note) => {
          if (note.trim()) void editPin(p.id, { note });
        }}
      />
      {p.bbox && (
        <p className="muted mono">
          {Object.entries(p.bbox)
            .map(([k, v]) => k + " " + v.toFixed(3))
            .join(" · ")}
        </p>
      )}
      <div className="between">
        已解决
        <Switch
          label="已解决"
          checked={p.status === "resolved"}
          onChange={(v) =>
            editPin(p.id, {
              status: v ? "resolved" : "open",
              resolved_by_revision: v ? timeline!.revision : null,
            })
          }
        />
      </div>
      <Button onClick={() => deletePin(p.id)}>
        <Trash2 />
        删除批注
      </Button>
    </>
  );
}
function ScreenTools({ clip }: { clip: Clip }) {
  const doc = useStudio((s) => s.timeline)!,
    accept = useStudio((s) => s.acceptTimeline),
    select = useStudio((s) => s.select);
  const [position, place] = useState("center");
  async function add(kind: string) {
    const start = Math.max(
      clip.start_ms,
      Math.min(
        Math.round((usePlayback.getState().frame * 1000) / doc.fps),
        clip.end_ms - 1,
      ),
    );
    const box = {
      x: position === "left" ? 0.12 : position === "right" ? 0.58 : 0.35,
      y: 0.32,
      w: 0.3,
      h: 0.18,
    };
    try {
      const next = await api.annotate(doc.project_id, doc.revision, {
        kind,
        start_ms: start,
        duration_ms: Math.min(2200, clip.end_ms - start),
        target_bbox: box,
        scale: 1.65,
        callout_text: kind === "callout_box" ? "点击此处" : "",
      });
      accept(next);
      const added = next.tracks.annotation.find(
        (c) => !doc.tracks.annotation.some((old) => old.id === c.id),
      );
      if (added && useStudio.getState().project?.id === doc.project_id)
        select({ track: "annotation", id: added.id });
    } catch (e) {
      report(e);
    }
  }
  return (
    <section className="screen-tools stack">
      <h3>录屏标注</h3>
      <Select
        label="标注区域"
        value={position}
        onChange={place}
        options={[
          { value: "left", label: "画面左侧" },
          { value: "center", label: "画面中央" },
          { value: "right", label: "画面右侧" },
        ]}
      />
      <div className="row">
        {[
          ["zoom_focus", "放大镜头"],
          ["spotlight", "聚光灯"],
          ["callout_box", "引导气泡"],
        ].map(([k, label]) => (
          <Button key={k} onClick={() => add(k)}>
            + {label}
          </Button>
        ))}
      </div>
    </section>
  );
}
function ClipInspector({ clip: c, track }: { clip: Clip; track: TrackName }) {
  const { patchTimeline, skills, media } = useStudio();
  const sourceDuration = media.find((a) => a.id === c.asset_id)?.duration_ms;
  const patch = (data: Partial<Clip>) =>
    patchTimeline(
      [{ op: "update_clip", track, clip_id: c.id, patch: data }],
      "编辑" + trackLabels[track] + "片段",
    );
  const templates =
    skills.find((s) => s.id === "motion-editorial")?.templates ?? [];
  const template = c.component_id ?? c.template_id ?? c.template ?? "cover",
    motion = c.kind === "motion_card",
    screen = track === "video" && !motion;
  const titleKey = headlineKey(template);
  const numeric = (
    label: string,
    key:
      | "start_ms"
      | "end_ms"
      | "source_in_ms"
      | "source_out_ms"
      | "speed"
      | "volume",
    min: number,
    max?: number,
  ) => (
    <Edit
      label={label}
      value={
        c[key] ??
        (key === "speed" || key === "volume"
          ? 1
          : key === "source_out_ms"
            ? (c.source_in_ms ?? 0) + (c.end_ms - c.start_ms) * (c.speed ?? 1)
            : 0)
      }
      type="number"
      min={min}
      max={max}
      step={key.endsWith("ms") ? 1 : undefined}
      save={(v) => {
        const value = Number(v);
        if (key === "speed" && (c.asset_id || c.src)) {
          const sourceLength =
            c.source_out_ms != null
              ? c.source_out_ms - (c.source_in_ms ?? 0)
              : (c.end_ms - c.start_ms) * (c.speed ?? 1);
          return patch({
            speed: value,
            end_ms: c.start_ms + Math.max(1, Math.round(sourceLength / value)),
          });
        }
        return patch({ [key]: value });
      }}
    />
  );
  const preset = c.screen_frame ?? c.frame_style,
    zoom = c.zoom_keyframes?.[0] ??
      preset?.zoom_keyframes?.[0] ?? [0, 1, 0.5, 0.5];
  const r = c.target_bbox ??
    c.rect ??
    c.target_rect ?? { x: 0.06, y: 0.09, w: 0.5, h: 0.12 };
  const fields = templates.find((t) => t.id === template)?.props_schema
    .properties as Record<string, { type: string | string[] }> | undefined;
  function updateProp(key: string, s: string) {
    if (fields?.[key]?.type === "array") {
      try {
        const parsed = JSON.parse(s);
        if (!Array.isArray(parsed)) throw Error();
        const valid = parsed.every((item) => {
          if (key === "bars")
            return (
              item &&
              typeof item.label === "string" &&
              Number.isFinite(item.value)
            );
          if (key === "items" || key === "steps")
            return (
              typeof item === "string" ||
              (item &&
                typeof item === "object" &&
                !Array.isArray(item) &&
                Object.values(item).every((v) => typeof v === "string"))
            );
          return typeof item === "string";
        });
        if (!valid) throw Error();
        void patch({ props: { [key]: parsed } });
      } catch {
        toast.error("请输入有效的 JSON 列表");
      }
    } else void patch({ props: { [key]: s } });
  }
  return (
    <>
      <h3>{trackLabels[track]}片段</h3>
      <div className="pair">
        {numeric("开始 (ms)", "start_ms", 0, c.end_ms - 1)}
        {numeric("结束 (ms)", "end_ms", c.start_ms + 1)}
      </div>
      {motion ? (
        <>
          <Field label="动效模板">
            <Select
              label="动效模板"
              value={template}
              options={templates.map((t) => ({ value: t.id, label: t.name }))}
              onChange={(v) =>
                patch({
                  component_id: v,
                  props: {
                    [headlineKey(v)]: c.props?.[headlineKey(v)] ?? clipName(c),
                  },
                })
              }
            />
          </Field>
          <Edit
            label="标题"
            value={c.props?.[titleKey] ?? ""}
            save={(v) => patch({ props: { [titleKey]: v } })}
          />
        </>
      ) : screen ? (
        <Field label="录屏包装">
          <Select
            label="录屏包装"
            value={
              preset?.padding === 0 ? "plain" : preset ? "window" : "plain"
            }
            options={[
              { value: "plain", label: "铺满画面" },
              { value: "window", label: "Screen Studio 圆角窗口" },
            ]}
            onChange={(v) =>
              patch({
                screen_frame: {
                  padding: v === "plain" ? 0 : 48,
                  rounded: v !== "plain",
                  borderRadius: v === "plain" ? 0 : 28,
                },
              })
            }
          />
        </Field>
      ) : track === "audio" ? (
        numeric("音量", "volume", 0, 1)
      ) : (
        <Edit
          label="文字"
          value={c.callout_text ?? c.text ?? ""}
          save={(v) =>
            patch(
              c.callout_text !== undefined ? { callout_text: v } : { text: v },
            )
          }
        />
      )}
      {track === "subtitle" && (
        <Field label="字幕样式">
          <Select
            label="字幕样式"
            value={c.style_preset || "inherit"}
            options={[{ value: "inherit", label: "跟随工程" }, ...styles]}
            onChange={(v) => patch({ style_preset: v === "inherit" ? "" : v })}
          />
        </Field>
      )}
      {(track === "annotation" || track === "overlay") && (
        <Field label="表现形式">
          <Select
            label="表现形式"
            value={c.kind}
            options={Array.from(
              new Set([
                c.kind,
                ...(track === "annotation"
                  ? ["zoom_focus", "spotlight", "cursor", "callout_box"]
                  : ["badge", "callout_box"]),
              ]),
            )}
            onChange={(kind) =>
              patch({ kind, spotlight: kind === "spotlight" })
            }
          />
        </Field>
      )}
      <details>
        <summary>更多</summary>
        <div className="stack">
          {motion && (
            <>
              <Edit
                label="标签"
                value={c.props?.tag ?? ""}
                save={(v) => patch({ props: { tag: v } })}
              />
              {Object.keys(fields ?? {})
                .filter((k) => k !== titleKey && k !== "tag")
                .map((k) => {
                  const val = c.props?.[k as keyof CardProps];
                  return (
                    <Edit
                      key={k}
                      label={k}
                      value={
                        Array.isArray(val)
                          ? JSON.stringify(val)
                          : String(
                              val ?? (fields?.[k].type === "array" ? "[]" : ""),
                            )
                      }
                      save={(v) => updateProp(k, v)}
                    />
                  );
                })}
            </>
          )}
          {screen && (
            <>
              <Edit
                label="窗口留白"
                type="number"
                min={0}
                max={240}
                value={preset?.padding ?? 0}
                save={(v) =>
                  patch({ screen_frame: { ...preset, padding: Number(v) } })
                }
              />
              <Field label="窗口背景">
                <Select
                  label="窗口背景"
                  value={
                    preset?.gradient ??
                    "linear-gradient(140deg,#374852,#897a70)"
                  }
                  options={[
                    {
                      value: "linear-gradient(140deg,#374852,#897a70)",
                      label: "岩灰",
                    },
                    {
                      value: "linear-gradient(140deg,#405369,#b2c4d0)",
                      label: "雾蓝",
                    },
                    {
                      value: "linear-gradient(140deg,#fbefe3,#d6b89a)",
                      label: "暖沙",
                    },
                  ]}
                  onChange={(gradient) =>
                    patch({ screen_frame: { ...preset, gradient } })
                  }
                />
              </Field>
              <div className="between">
                窗口圆角
                <Switch
                  label="窗口圆角"
                  checked={
                    !!preset &&
                    preset.rounded !== false &&
                    preset.borderRadius !== 0
                  }
                  onChange={(rounded) =>
                    patch({
                      screen_frame: {
                        ...preset,
                        rounded,
                        borderRadius: rounded ? 28 : 0,
                      },
                    })
                  }
                />
              </div>
            </>
          )}
          {c.kind === "zoom_focus" && (
            <Edit
              label="放大倍率"
              type="number"
              min={1}
              max={4}
              value={c.scale ?? c.zoom_scale ?? 1.65}
              save={(v) => patch({ scale: Number(v) })}
            />
          )}
          {screen &&
            [
              ["聚焦 X", 2],
              ["聚焦 Y", 3],
              ["缩放", 1],
            ].map(([label, n]) => (
              <Edit
                key={label}
                label={String(label)}
                type="number"
                min={n === 1 ? 1 : 0}
                max={n === 1 ? 5 : 1}
                value={zoom[Number(n)]}
                save={(v) => {
                  const z = [...zoom] as [number, number, number, number];
                  z[Number(n)] = Number(v);
                  void patch({
                    zoom_keyframes: [
                      z,
                      ...(
                        c.zoom_keyframes ??
                        preset?.zoom_keyframes ??
                        []
                      ).slice(1),
                    ],
                  });
                }}
              />
            ))}
          {track === "subtitle" && (
            <Edit
              label="字幕底部留白 (%)"
              type="number"
              min={0}
              max={90}
              value={Math.round((c.caption_bottom ?? 0.065) * 1000) / 10}
              save={(v) => patch({ caption_bottom: Number(v) / 100 })}
            />
          )}
          {track === "subtitle" && (
            <Edit
              label="高亮词（逗号分隔）"
              value={(c.highlight_words ?? []).join(", ")}
              save={(v) =>
                patch({
                  highlight_words: v
                    .split(/[,，]/)
                    .map((w) => w.trim())
                    .filter(Boolean),
                })
              }
            />
          )}
          {(track === "annotation" || track === "overlay") && (
            <div className="pair">
              {(["x", "y", "w", "h"] as const).map((k) => (
                <Edit
                  type="number"
                  key={k}
                  label={"区域 " + k.toUpperCase()}
                  min={k === "x" || k === "y" ? 0 : 0.01}
                  max={
                    k === "x"
                      ? 1 - r.w
                      : k === "y"
                        ? 1 - r.h
                        : k === "w"
                          ? 1 - r.x
                          : 1 - r.y
                  }
                  value={r[k]}
                  save={(v) =>
                    patch({
                      [track === "annotation" ? "target_bbox" : "rect"]: {
                        ...r,
                        [k]: Number(v),
                      },
                    })
                  }
                />
              ))}
            </div>
          )}
          {numeric("速度", "speed", 0.1, 8)}
          {track !== "audio" && numeric("音量", "volume", 0, 1)}
          {numeric(
            "源入点 (ms)",
            "source_in_ms",
            0,
            c.source_out_ms ? c.source_out_ms - 1 : undefined,
          )}
          {numeric(
            "源出点 (ms)",
            "source_out_ms",
            (c.source_in_ms ?? 0) + 1,
            sourceDuration ?? undefined,
          )}
        </div>
      </details>
      {screen && <ScreenTools clip={c} />}
    </>
  );
}
export function InspectorPanel() {
  const {
    timeline: doc,
    selection,
    select,
    pins,
    media,
    patchTimeline,
  } = useStudio();
  if (!doc) return null;
  const clip =
    selection && "id" in selection
      ? doc.tracks[selection.track].find((c) => c.id === selection.id)
      : undefined;
  const pin =
    selection && "pin" in selection
      ? pins.find((p) => p.id === selection.pin)
      : undefined;
  return (
    <aside className="inspector">
      <div className="heading">
        <h2>
          <SlidersHorizontal />
          检视器
        </h2>
        {selection && (
          <Button variant="ghost" onClick={() => select(null)}>
            工程设置
          </Button>
        )}
      </div>
      <div className="inspector-body stack">
        {pin ? (
          <PinInspector key={pin.id} pin={pin} />
        ) : clip && selection && "track" in selection ? (
          <ClipInspector key={clip.id} clip={clip} track={selection.track} />
        ) : (
          <>
            <h3>工程设置</h3>
            {doc.skill_id === "screen-tutorial" &&
              doc.tracks.video.some((c) => c.asset_id) && (
                <ScreenTools clip={doc.tracks.video.find((c) => c.asset_id)!} />
              )}
            <Field label="导出画幅">
              <AspectControl />
            </Field>
            <Field label="字幕样式">
              <Select
                label="全局字幕样式"
                value={
                  typeof doc.subtitle_style === "string"
                    ? doc.subtitle_style
                    : (doc.subtitle_style.preset ?? "pill_dark")
                }
                options={styles}
                onChange={(v) =>
                  patchTimeline(
                    [{ op: "set_subtitle_style", subtitle_style: v }],
                    "更改字幕样式",
                  )
                }
              />
            </Field>
            <Field label="背景音乐">
              <Select
                label="背景音乐"
                value={doc.bgm?.asset_id ?? "none"}
                options={[
                  { value: "none", label: "无配乐" },
                  ...media
                    .filter((a) => a.kind === "audio")
                    .map((a) => ({ value: a.id, label: a.filename })),
                ]}
                onChange={(v) =>
                  patchTimeline(
                    [
                      {
                        op: "set_bgm",
                        bgm:
                          v === "none"
                            ? null
                            : { asset_id: v, volume: 0.35, loop: true },
                      },
                    ],
                    "更改背景音乐",
                  )
                }
              />
            </Field>
            {doc.bgm && (
              <details>
                <summary>更多</summary>
                <div className="stack">
                  <Edit
                    label="配乐音量"
                    type="number"
                    min={0}
                    max={1}
                    value={doc.bgm.volume ?? 0.35}
                    save={(v) =>
                      patchTimeline(
                        [
                          {
                            op: "set_bgm",
                            bgm: { ...doc.bgm, volume: Number(v) },
                          },
                        ],
                        "调整配乐音量",
                      )
                    }
                  />
                  <div className="between">
                    循环播放
                    <Switch
                      label="循环播放"
                      checked={doc.bgm.loop !== false}
                      onChange={(loop) =>
                        patchTimeline(
                          [{ op: "set_bgm", bgm: { ...doc.bgm, loop } }],
                          "更改配乐循环",
                        )
                      }
                    />
                  </div>
                </div>
              </details>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
