import type { Clip, MediaAsset, TimelineDocument, TrackName } from "@/types";
import { durationMs } from "@motion/types";

export const modes = [
  {
    id: "screen-tutorial",
    name: "系统录屏精剪",
    caption: "裁切录屏、聚焦操作细节，用画框批注对齐每一帧。",
    short: "录屏精剪",
  },
  {
    id: "ai-news-montage",
    name: "AI 资讯混剪",
    caption: "将新闻素材、动效卡与配乐编排成一条资讯短片。",
    short: "资讯混剪",
  },
  {
    id: "motion-editorial",
    name: "动效图文科普",
    caption: "用九种动态模板，把数字、观点与步骤讲清楚。",
    short: "动效科普",
  },
] as const;
export const modeFor = (id?: string | null) =>
  modes.find((m) => m.id === id) || modes[2];
export const aspects = ["16:9", "9:16", "1:1"] as const;
export const trackLabels: Record<TrackName, string> = {
  video: "主视频",
  overlay: "贴片",
  annotation: "标注",
  subtitle: "字幕",
  audio: "音频",
};
export const tracks = Object.keys(trackLabels) as TrackName[];
export const timecode = (ms: number) => {
  const cs = Math.max(0, Math.floor(ms / 10));
  return (
    [Math.floor(cs / 6000), Math.floor(cs / 100) % 60]
      .map((v) => String(v).padStart(2, "0"))
      .join(":") +
    "." +
    String(cs % 100).padStart(2, "0")
  );
};
export const headlineKey = (template: string) =>
  template === "quote"
    ? "quote"
    : ["stat", "compare", "steps", "timeline_card", "image_card"].includes(
          template,
        )
      ? "heading"
      : "title";
export const clipName = (c: Clip) =>
  c.props?.[
    headlineKey(c.component_id ?? c.template_id ?? c.template ?? "cover")
  ] ||
  c.props?.title ||
  c.props?.heading ||
  c.props?.quote ||
  c.props?.label ||
  c.text ||
  c.callout_text ||
  c.prompt_hint ||
  { video_clip: "录屏片段", image_clip: "静态图片", bgm: "背景音乐" }[c.kind] ||
  c.kind;
export const makeCard = (
  start: number,
  title: string,
  tag = "动效图文",
): Clip => ({
  id: crypto.randomUUID(),
  kind: "motion_card",
  component_id: "cover",
  start_ms: start,
  end_ms: start + 3000,
  props: { title, tag },
});
export function assetClip(
  asset: MediaAsset,
  doc: TimelineDocument,
): { track: TrackName; clip: Clip } {
  const track = asset.kind === "audio" ? "audio" : "video";
  const start =
    track === "audio"
      ? 0
      : Math.max(0, ...doc.tracks.video.map((c) => c.end_ms));
  return {
    track,
    clip: {
      id: crypto.randomUUID(),
      asset_id: asset.id,
      kind: asset.kind === "audio" ? "bgm" : asset.kind + "_clip",
      start_ms: start,
      end_ms: start + (asset.duration_ms || 3000),
      text: asset.filename,
      ...(asset.kind === "video" && doc.skill_id === "screen-tutorial"
        ? { screen_frame: { rounded: true, padding: 48 } }
        : {}),
    },
  };
}
export const endOf = durationMs;
