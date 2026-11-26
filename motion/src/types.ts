export type TrackName =
  | "video"
  | "overlay"
  | "annotation"
  | "subtitle"
  | "audio";
export type Rect = { x: number; y: number; w: number; h: number };
export type Zoom = [number, number, number, number];
export type ScreenFrame = {
  padding?: number;
  borderRadius?: number;
  border_radius?: number;
  rounded?: boolean;
  gradient?: string;
  wallpaper?: string;
  zoom_keyframes?: Zoom[];
};
type Point = {
  label?: string;
  title?: string;
  desc?: string;
  detail?: string;
  step_label?: string;
};
export interface CardProps {
  title?: string;
  heading?: string;
  tag?: string;
  subtitle?: string;
  text?: string;
  body?: string;
  metric?: string | number;
  value?: string | number;
  unit?: string;
  label?: string;
  context?: string;
  delta?: string;
  bars?: { label: string; value: number; accent?: string }[];
  takeaway?: string;
  left_title?: string;
  right_title?: string;
  left_points?: string[];
  right_points?: string[];
  items?: (string | Point)[];
  steps?: (string | Point)[];
  quote?: string;
  attribution?: string;
  code?: string;
  language?: string;
  caption?: string;
  src?: string;
}
export type SubtitleStyle =
  | string
  | {
      preset?: string;
      font_size?: number;
      color?: string;
      background?: string;
      bottom?: number;
    };
export interface Clip {
  id: string;
  kind: string;
  start_ms: number;
  end_ms: number;
  src?: string;
  asset_id?: string;
  component_id?: string;
  template?: string;
  template_id?: string;
  props?: CardProps;
  source_state?: string;
  source_in_ms?: number;
  source_out_ms?: number | null;
  speed?: number;
  volume?: number;
  text?: string;
  prompt_hint?: string;
  rect?: Rect;
  target_rect?: Rect;
  target_bbox?: Rect;
  scale?: number;
  transcript_segment_id?: string;
  callout_text?: string;
  style_preset?: string;
  highlight_words?: string[];
  caption_bottom?: number;
  border_radius?: number;
  spotlight?: boolean;
  zoom_scale?: number;
  screen_frame?: ScreenFrame;
  frame_style?: ScreenFrame;
  zoom_keyframes?: Zoom[];
  crop?: { mode?: "contain" | "cover"; focus_x?: number; focus_y?: number };
  transition_out?: { type: string; duration_ms: number };
  fade_in_ms?: number;
  fade_out_ms?: number;
  ducking_db?: number;
}
export type Music = Partial<Clip> & { loop?: boolean };
export interface TimelineDocument {
  version: "3.0";
  project_id: string;
  revision: number;
  fps: number;
  aspect_ratio: "16:9" | "9:16" | "1:1" | "3:4";
  resolution: { width: number; height: number };
  tracks: Record<TrackName, Clip[]>;
  bgm: Music | null;
  subtitle_style: SubtitleStyle;
  export: Record<string, unknown>;
  meta: Record<string, unknown>;
  theme?: string;
  skill_id?: string;
}
export const frames = (ms: number, fps: number) =>
  Math.round((ms * fps) / 1000);
export const durationMs = (doc: TimelineDocument) =>
  Math.max(
    0,
    ...Object.values(doc.tracks)
      .flat()
      .map((c) => c.end_ms),
  );
