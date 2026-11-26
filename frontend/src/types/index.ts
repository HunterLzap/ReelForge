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
  | { op: "delete_clip"; track: TrackName; clip_id: string }
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

export type IssueKind = "silence" | "filler" | "retake";
export interface WordToken {
  id: string;
  text: string;
  start_ms: number;
  end_ms: number;
  deleted: boolean;
  tag: "normal" | "filler" | "pause";
}
export interface TranscriptSegment {
  id: string;
  text: string;
  start_ms: number;
  end_ms: number;
  words: WordToken[];
}
export interface TranscriptDocument {
  asset_id: string;
  engine: string;
  hotwords: string[];
  segments: TranscriptSegment[];
}
export interface RoughCutIssue {
  id: string;
  kind: IssueKind;
  start_ms: number;
  end_ms: number;
  text: string;
  word_ids: string[];
}
export interface TranscriptState {
  transcript: TranscriptDocument;
  issues: RoughCutIssue[];
  base_revision: number;
}
export interface RoughCutPreview {
  issues: RoughCutIssue[];
  saved_ms: number;
  base_revision: number;
  timeline: TimelineDocument | null;
}
export interface RoughCutRequest {
  base_revision: number;
  apply?: boolean;
  buffer_ms?: number;
  delete_word_ids?: string[];
  issue_ids?: string[];
  cut_ranges_ms?: [number, number][];
}
export type Slot =
  | "llm_director"
  | "vlm_vision"
  | "asr_speech"
  | "tts_voice"
  | "crawler_extract";
export interface ModelConfig {
  provider: string;
  model: string;
  base_url: string;
  api_key_env: string;
  enabled: boolean;
  model_size_mb: number;
  extra: Record<string, unknown>;
}
export interface HardwarePolicy {
  active_profile: string;
  recommended_profile: string;
  guarded: boolean;
  guard_explanation: string;
}
export interface Hardware extends HardwarePolicy {
  cpu_cores: number;
  ram_total_gb: number;
  ram_available_gb: number;
  disk_free_gb: number;
  disk_total_gb: number;
  binaries: Record<string, boolean>;
  services: Record<string, boolean>;
  gpu: { cuda: boolean; mps: boolean };
}
export interface CatalogEntry {
  id: string;
  slot: Slot;
  provider: string;
  size_mb: number;
  mirrors: string[];
}
export interface ModelCenter extends HardwarePolicy {
  slots: Record<Slot, ModelConfig>;
  catalog: CatalogEntry[];
  presets: {
    id: string;
    name: string;
    base_url: string;
    api_key_env: string;
    model: string;
  }[];
}
export interface DownloadTask {
  task_id: string;
  model: string;
  status: string;
  percentage: number;
  downloaded_bytes: number;
  total_bytes: number;
  error?: string;
  mock: boolean;
}

export type SourceState =
  "local_matched" | "web_fetched" | "motion_generated" | "placeholder";
export interface Shot {
  id: string;
  title: string;
  narration: string;
  visual_query: string;
  duration_ms: number;
  source_state: SourceState;
  asset_id?: string | null;
  source_url?: string | null;
  component_id?: string | null;
  props?: Clip["props"];
  placeholder_hint?: string | null;
}
export interface Turn {
  role: "user" | "assistant";
  content: string;
}
export interface Brief {
  skill_id: string;
  aspect_ratio: Aspect;
  base_revision?: number;
}
export interface LibraryItem {
  id: string;
  filename: string;
  rel_path: string;
  kind: MediaAsset["kind"];
  thumbnail_url: string | null;
  quality_flags: string[];
  tags: string[];
  caption: string;
}
export interface SourceHit {
  thumbnail_url?: string;
  url: string;
  media_url?: string;
  title: string;
  license: string;
  kind: string;
}
export interface PasteInput {
  image_data_url?: string;
  url?: string;
  filename?: string;
  slot_clip_id?: string;
  track?: TrackName;
  base_revision?: number;
}
