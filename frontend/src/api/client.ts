import type {
  Brief,
  Shot,
  Turn,
  LibraryItem,
  SourceHit,
  PasteInput,
  Project,
  ExportResult,
  PurgeScope,
  Skill,
  TimelineDocument,
  TimelineOp,
  Revision,
  ReviewPin,
  PinCreate,
  MediaAsset,
  StorageInfo,
  Aspect,
  Hardware,
  ModelCenter,
  ModelConfig,
  Slot,
  DownloadTask,
  TranscriptDocument,
  TranscriptState,
  RoughCutPreview,
  RoughCutRequest,
  Rect,
} from "@/types";

const params = new URL(location.href);
if (params.searchParams.has("token")) {
  localStorage.setItem(
    "reelforge_token",
    params.searchParams.get("token") || "",
  );
  params.searchParams.delete("token");
  history.replaceState(null, "", params);
}
const token = () => localStorage.getItem("reelforge_token");
export function resourceUrl(path: string) {
  const url = new URL(path, location.origin);
  if (
    url.origin === location.origin &&
    /^\/(api|workspace)\//.test(url.pathname) &&
    token()
  )
    url.searchParams.set("token", token()!);
  return url.href;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    detail: string,
  ) {
    super(detail);
  }
}
function failure(status: number, detail?: unknown) {
  if (status === 401) window.dispatchEvent(new Event("reelforge:auth"));
  return new ApiError(
    status,
    typeof detail === "string"
      ? detail
      : status === 507
        ? "磁盘配额不足，请清理缓存"
        : "请求失败 (" + status + ")",
  );
}
async function json<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const headers = new Headers();
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (token()) headers.set("Authorization", "Bearer " + token());
  const res = await fetch(path, {
    method,
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok)
    throw failure(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
}
function request<T>(path: string, method = "GET", data?: unknown) {
  return json<T>("/api/projects" + path, method, data);
}
export const api = {
  directorChat: (
    pid: string,
    body: Brief & { message: string; history: Turn[]; web_enabled: boolean },
  ) =>
    request<{ reply: string; shots: Shot[]; base_revision: number }>(
      "/" + pid + "/director/chat",
      "POST",
      body,
    ),
  directorPlan: (pid: string, body: Brief & { shots: Shot[] }) =>
    request<TimelineDocument>("/" + pid + "/director/plan", "POST", body),
  libraryIndex: (path: string, aspect: Aspect) =>
    json<{ items: LibraryItem[]; errors: { path: string; message: string }[] }>(
      "/api/library/index",
      "POST",
      { path, aspect },
    ),
  librarySearch: (q: string) =>
    json<LibraryItem[]>("/api/library/search?q=" + encodeURIComponent(q)),
  libraryImport: (pid: string, id: string) =>
    request<MediaAsset>("/" + pid + "/library/" + id + "/import", "POST"),
  sourceSearch: (pid: string, q: string, kind: string) =>
    request<{ results: SourceHit[] }>("/" + pid + "/sourcing/search", "POST", {
      q,
      kind,
    }),
  sourceFetch: (
    pid: string,
    body: {
      url: string;
      license?: string;
      media_url?: string;
      use_browser?: boolean;
    },
  ) =>
    request<{ asset: MediaAsset; strategy: string }>(
      "/" + pid + "/sourcing/fetch",
      "POST",
      body,
    ),
  paste: (pid: string, body: PasteInput) =>
    request<{ asset: MediaAsset; timeline: TimelineDocument | null }>(
      "/" + pid + "/sourcing/paste",
      "POST",
      body,
    ),
  probe: () => json<Hardware>("/api/system/probe", "POST"),
  models: () => json<ModelCenter>("/api/models"),
  saveModel: (slot: Slot, config: ModelConfig) =>
    json<ModelConfig>("/api/models/" + slot, "PUT", config),
  testModel: (slot: Slot) =>
    json<{ ok: boolean; message: string }>("/api/models/test", "POST", {
      slot,
    }),
  downloadEvents: () => new EventSource(resourceUrl("/api/models/downloads")),
  downloads: () => json<DownloadTask[]>("/api/models/downloads"),
  download: (model: string, mirror: string) =>
    json<DownloadTask>("/api/models/download", "POST", { model, mirror }),
  cancelDownload: (id: string) =>
    json<DownloadTask>("/api/models/downloads/" + id + "/cancel", "POST"),
  engines: () => json<{ mcp_config: object }>("/api/system/engines"),
  transcript: (pid: string) =>
    request<TranscriptState>("/" + pid + "/transcript"),
  transcribe: (pid: string, base_revision: number, asset_id?: string) =>
    request<TranscriptDocument>("/" + pid + "/transcribe", "POST", {
      base_revision,
      asset_id,
    }),
  roughCut: (pid: string, body: RoughCutRequest) =>
    request<RoughCutPreview>("/" + pid + "/rough-cut", "POST", body),
  syncSubtitles: (pid: string, base_revision: number) =>
    request<TimelineDocument>(
      "/" + pid + "/transcript/sync-subtitles",
      "POST",
      { base_revision },
    ),
  replaceTerms: (
    pid: string,
    base_revision: number,
    find: string,
    replace: string,
  ) =>
    request<{ timeline: TimelineDocument; replaced_count: number }>(
      "/" + pid + "/subtitles/batch-replace",
      "POST",
      { base_revision, find, replace },
    ),
  subtitlesUrl: (pid: string, format: "ass" | "srt") =>
    resourceUrl("/api/projects/" + pid + "/subtitles/export?format=" + format),
  annotate: (
    pid: string,
    base_revision: number,
    clip: {
      kind: string;
      start_ms: number;
      duration_ms: number;
      target_bbox: Rect;
      scale?: number;
      callout_text?: string;
    },
  ) =>
    request<TimelineDocument>("/" + pid + "/annotations/zoom", "POST", {
      ...clip,
      base_revision,
    }),
  events: (pid: string) =>
    new EventSource(resourceUrl("/api/projects/" + pid + "/stream")),
  projects: () => request<Project[]>(""),
  project: (pid: string) => request<Project>("/" + pid),
  create: (
    topic: string,
    skill_id: string,
    aspect_ratio: Aspect,
    seed_materials: string,
  ) =>
    request<Project>("", "POST", {
      topic,
      skill_id,
      aspect_ratio,
      seed_materials,
      target_format: aspect_ratio === "9:16" ? "video_9_16" : "video_16_9",
    }),
  remove: (pid: string) => request("/" + pid, "DELETE"),
  skills: () => json<Skill[]>("/api/skills"),
  timeline: (pid: string) => request<TimelineDocument>("/" + pid + "/timeline"),
  patch: (
    pid: string,
    base_revision: number,
    ops: TimelineOp[],
    summary: string,
  ) =>
    request<TimelineDocument>("/" + pid + "/timeline/patch", "POST", {
      base_revision,
      ops,
      summary,
    }),
  history: (pid: string, direction: "undo" | "redo", base_revision: number) =>
    request<TimelineDocument>("/" + pid + "/timeline/" + direction, "POST", {
      base_revision,
    }),
  revisions: (pid: string) =>
    request<Revision[]>("/" + pid + "/timeline/revisions"),
  export: (pid: string) =>
    request<ExportResult>("/" + pid + "/timeline/export", "POST"),
  pins: (pid: string) => request<ReviewPin[]>("/" + pid + "/pins"),
  pin: (pid: string, data: PinCreate) =>
    request<ReviewPin>("/" + pid + "/pins", "POST", data),
  editPin: (
    pid: string,
    id: string,
    data: Partial<Pick<ReviewPin, "note" | "status" | "resolved_by_revision">>,
  ) => request<ReviewPin>("/" + pid + "/pins/" + id, "PATCH", data),
  deletePin: (pid: string, id: string) =>
    request("/" + pid + "/pins/" + id, "DELETE"),
  frame: (pin: ReviewPin) => resourceUrl(pin.frame_url),
  media: (pid: string) => request<MediaAsset[]>("/" + pid + "/media"),
  stream: (id: string) =>
    resourceUrl(
      "/api/media/" + encodeURIComponent(id) + "/stream?variant=proxy",
    ),
  storage: () => json<StorageInfo>("/api/system/storage"),
  purge: (project_id?: string, scope: PurgeScope = "temp") =>
    json<{ freed_bytes: number }>("/api/system/storage/purge", "POST", {
      project_id,
      scope,
    }),
  upload(
    pid: string,
    file: File,
    progress: (percent: number) => void,
  ): Promise<MediaAsset> {
    const data = new FormData();
    data.append("project_id", pid);
    data.append("file", file);
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/media/upload");
      if (token()) xhr.setRequestHeader("Authorization", "Bearer " + token());
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable)
          progress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onload = () =>
        xhr.status >= 200 && xhr.status < 300
          ? resolve(xhr.response)
          : reject(failure(xhr.status, xhr.response?.detail));
      xhr.onerror = () => reject(new Error("上传连接中断"));
      xhr.send(data);
    });
  },
};
