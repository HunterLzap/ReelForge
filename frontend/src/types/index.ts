export type Format = "video_16_9" | "video_9_16" | "cards_3_4";
export interface Project {
  id: string;
  topic: string;
  target_format: Format;
  theme: string;
  voice: string;
  auto_approve: boolean;
  status: string;
  error_message: string | null;
  updated_at: string;
  total_tokens: number;
  estimated_cost_cny: number;
}
export interface Scene {
  id: string;
  order_index: number;
  template_type: string;
  narration: string;
  visual_payload: Record<string, unknown>;
  source_ids: string[];
  duration_ms: number;
  content_hash: string | null;
  render_status: string;
}
export interface Source {
  id: string;
  title: string;
  url: string;
  snippet: string;
  credibility_note: string;
}
export interface Detail extends Project {
  research: { outline: string[] } | null;
  fact_check: { approved: boolean; summary: string; issues: string[] } | null;
  scenes: Scene[];
  sources: Source[];
  logs: {
    id: number;
    stage_name: string;
    message: string;
    created_at: string;
  }[];
  stage_runs: { stage_name: string; duration_ms: number }[];
}
export const formats: Record<Format, string> = {
  video_16_9: "16:9 横屏视频",
  video_9_16: "9:16 竖屏视频",
  cards_3_4: "3:4 图文卡片",
};
export const states: Record<string, string> = {
  PENDING: "待启动",
  RESEARCHING: "采编中",
  FACT_CHECKING: "核查中",
  WAITING_OUTLINE: "待确认大纲",
  DIRECTING: "分镜设计中",
  WAITING_STORYBOARD: "待确认分镜",
  RENDERING: "渲染中",
  ASSEMBLING: "合成中",
  COMPLETED: "已完成",
  FAILED: "运行失败",
};
export type Act = (
  path: string,
  method?: string,
  data?: unknown,
) => Promise<boolean>;
