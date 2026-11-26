import type {
  TimelineDocument,
  TrackName,
  Clip,
  Rect,
  Music,
  SubtitleStyle,
} from "@motion/types";
export type { TimelineDocument, TrackName, Clip, Rect } from "@motion/types";
export type Aspect = TimelineDocument["aspect_ratio"];
export interface Project {
  id: string;
  status: string;
  topic: string;
  updated_at: string;
  created_at: string;
  skill_id?: string | null;
  aspect_ratio?: Aspect | null;
  timeline_revision?: number | null;
  seed_materials?: string;
}
export interface Skill {
  id: string;
  name: string;
  description: string;
  version: string;
  supported_aspects: Aspect[];
  inputs: Record<string, unknown>;
  templates: {
    id: string;
    name: string;
    props_schema: Record<string, unknown>;
  }[];
}
export interface Revision {
  revision: number;
  op_summary: string;
  author: string;
  created_at: string;
}
export type TimelineOp =
  | { op: "add_clip"; track: TrackName; clip: Clip }
  | {
      op: "update_clip";
      track: TrackName;
      clip_id: string;
      patch: Partial<Clip>;
    }
  | { op: "split_clip"; track: TrackName; clip_id: string; at_ms: number }
  | { op: "ripple_delete"; track: TrackName | "all"; clip_id: string }
  | { op: "set_export_spec"; export: TimelineDocument["export"] }
  | { op: "set_bgm"; bgm: Music | null }
  | { op: "set_subtitle_style"; subtitle_style: SubtitleStyle };
export interface PinCreate {
  time_ms: number;
  bbox: Rect | null;
  note: string;
  revision: number;
  track?: TrackName | null;
  clip_id?: string | null;
  frame_data_url?: string;
}
export interface ReviewPin extends Omit<PinCreate, "frame_data_url"> {
  created_at: string;
  frame_path: string;
  id: string;
  project_id: string;
  status: "open" | "resolved" | "dismissed";
  frame_url: string;
  resolved_by_revision: number | null;
}
export interface MediaAsset {
  id: string;
  project_id: string;
  kind: "video" | "image" | "audio";
  filename: string;
  path: string;
  proxy_path: string | null;
  duration_ms: number | null;
  size_bytes: number;
  width: number | null;
  height: number | null;
  mime_type: string;
  fps: number | null;
  sha256: string;
  source_type: string;
  source_url: string | null;
  license: string | null;
  created_at: string;
}
export interface StorageInfo {
  workspace_bytes: number;
  pins_bytes: number;
  models_bytes: number;
  project_breakdown: Record<string, number>;
  used_bytes: number;
  disk_limit_bytes: number;
  proxies_bytes: number;
  exports_bytes: number;
  usage_ratio: number;
  status: "ok" | "warning" | "critical";
}

export interface ExportResult {
  path: string;
  revision: number;
  url: string;
  width: number;
  height: number;
  fps: number;
  duration_ms: number;
}
export type PurgeScope = "temp" | "proxies" | "all_cache" | "exports";
export type Stage = "plan" | "edit" | "delivery";
export type Selection =
  { track: TrackName; id: string } | { pin: string } | null;
