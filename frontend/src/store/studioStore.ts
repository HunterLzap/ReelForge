import { create } from "zustand";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { optimistic } from "./optimistic";
import type {
  TimelineDocument,
  TimelineOp,
  EditDiff,
  Shot,
  Turn,
  Brief,
  Project,
  Skill,
  MediaAsset,
  ReviewPin,
  PinCreate,
  StorageInfo,
  Selection,
  Stage,
  ExportResult,
  PurgeScope,
} from "@/types";

export const report = (error: unknown) =>
  toast.error(error instanceof Error ? error.message : "操作失败，请重试");
type ExportState = {
  status: "idle" | "rendering" | "done" | "error";
  result?: ExportResult;
  message?: string;
};
export interface Draft extends Brief {
  shots: Shot[];
  history: Turn[];
}
interface Studio {
  draft: Draft | null;
  railTab: string;
  setRailTab: (tab: string) => void;
  setDraft: (pid: string, draft: Draft) => void;
  receiveMedia: (asset: MediaAsset) => void;
  refreshMedia: (pid: string) => Promise<void>;
  modelCenter: "models" | "probe" | null;
  showModels: (view: "models" | "probe" | null) => void;
  acceptTimeline: (timeline: TimelineDocument) => void;
  projects: Project[];
  skills: Skill[];
  project: Project | null;
  timeline: TimelineDocument | null;
  pins: ReviewPin[];
  media: MediaAsset[];
  storage: StorageInfo | null;
  selection: Selection;
  stage: Stage;
  busy: boolean;
  uploadProgress: number | null;
  delivery: ExportState;
  refreshHome: () => Promise<void>;
  open: (p: Project) => Promise<void>;
  close: () => void;
  select: (s: Selection) => void;
  setStage: (s: Stage) => void;
  patchTimeline: (ops: TimelineOp[], summary: string) => Promise<boolean>;
  aiEdits: (EditDiff & { message: string })[];
  aiEdit: (
    input: { pin: ReviewPin } | { message: string; timeMs: number },
  ) => Promise<boolean>;
  undoAi: (revision: number) => Promise<boolean>;
  undo: () => Promise<boolean>;
  redo: () => Promise<boolean>;
  addPin: (data: PinCreate) => Promise<ReviewPin | undefined>;
  editPin: (
    id: string,
    data: Partial<Pick<ReviewPin, "status" | "note" | "resolved_by_revision">>,
  ) => Promise<void>;
  deletePin: (id: string) => Promise<void>;
  upload: (file: File) => Promise<MediaAsset | undefined>;
  refreshStorage: () => Promise<void>;
  purge: (scope: PurgeScope) => Promise<void>;
  exportTimeline: () => Promise<void>;
}
const idle: ExportState = { status: "idle" };
export const useStudio = create<Studio>((set, get) => {
  let session = 0,
    stream: EventSource | undefined,
    pinRequest = 0;
  let seenRevision = -1;
  const active = (n: number) => n === session;
  async function refreshTimeline(pid: string, n: number) {
    const doc = await api.timeline(pid);
    if (
      active(n) &&
      !get().busy &&
      doc.revision >= (get().timeline?.revision ?? 0)
    )
      set({ timeline: doc });
  }
  async function refreshPins(pid: string, n: number) {
    const order = ++pinRequest,
      pins = await api.pins(pid);
    if (active(n) && order === pinRequest) set({ pins });
  }
  function receiveDelivery(name: string, message: string) {
    if (name === "error") set({ delivery: { status: "error", message } });
    else if (name === "export_done")
      set({ delivery: { status: "done", result: JSON.parse(message) } });
    else if (JSON.parse(message).stage === "render")
      set({ delivery: { status: "rendering" } });
  }
  function connect(pid: string, n: number, after: number) {
    stream = api.events(pid, after);
    let refreshing = false,
      pending = false;
    async function sync() {
      pending = true;
      if (refreshing) return;
      refreshing = true;
      try {
        while (pending && active(n)) {
          pending = false;
          await Promise.all([refreshTimeline(pid, n), refreshPins(pid, n)]);
        }
      } finally {
        refreshing = false;
      }
    }
    for (const name of [
      "timeline_updated",
      "pin_created",
      "pin_resolved",
      "pin_updated",
    ])
      stream.addEventListener(name, (e) => {
        if (!active(n)) return;
        const message = JSON.parse(e.data).message;
        // Older Pin events carry a bare ID.
        const detail = message.startsWith("{") ? JSON.parse(message) : {};
        if (name === "timeline_updated")
          seenRevision = Math.max(seenRevision, detail.revision);
        if (detail.author === "external_mcp")
          toast.info(
            name === "pin_resolved"
              ? "外部 MCP 已解决批注"
              : "外部 MCP 已更新时间轴",
          );
        void sync().catch(report);
      });
    for (const name of ["stage", "export_done", "error"])
      stream.addEventListener(name, (e) => {
        if (!active(n) || !(e instanceof MessageEvent)) return;
        receiveDelivery(name, JSON.parse(e.data).message);
      });
  }
  async function change(
    direction: "patch" | "undo" | "redo",
    ops: TimelineOp[] = [],
    summary = "",
  ) {
    const { timeline: before, busy } = get(),
      n = session;
    if (!before) return false;
    if (busy) {
      toast.info("正在保存上一次编辑，请稍后重试");
      return false;
    }
    const pid = before.project_id;
    set({
      busy: true,
      timeline: direction === "patch" ? optimistic(before, ops) : before,
    });
    try {
      const doc =
        direction === "patch"
          ? await api.patch(pid, before.revision, ops, summary)
          : await api.history(pid, direction, before.revision);
      if (active(n)) {
        set({ timeline: doc });
        if (direction !== "patch") await refreshPins(pid, n).catch(report);
      }
      return active(n);
    } catch (error) {
      if (active(n)) {
        set({ timeline: before });
        if (error instanceof ApiError && error.status === 409) {
          try {
            const doc = await api.timeline(pid);
            if (active(n)) {
              set({ timeline: doc });
              toast.info(
                doc.revision !== before.revision
                  ? "时间轴已被更新，已载入最新修订"
                  : error.message,
              );
            }
          } catch (refreshError) {
            report(refreshError);
          }
        } else report(error);
      }
      return false;
    } finally {
      if (active(n)) {
        set({ busy: false });
        if (seenRevision > (get().timeline?.revision ?? 0))
          void refreshTimeline(pid, n).catch(report);
      }
    }
  }
  return {
    draft: null,
    aiEdits: [],
    async aiEdit(input) {
      const { timeline: doc, busy, selection, aiEdits } = get();
      if (!doc || busy) return false;
      const n = session,
        pid = doc.project_id;
      set({ busy: true });
      try {
        const result =
          "pin" in input
            ? await api.fixPin(pid, input.pin.id, doc.revision)
            : await api.chatEdit(pid, {
                message: input.message,
                current_time_ms: input.timeMs,
                base_revision: doc.revision,
                selected_clip_id:
                  selection && "id" in selection ? selection.id : undefined,
                selected_track:
                  selection && "track" in selection
                    ? selection.track
                    : undefined,
                history: aiEdits.slice(-10).flatMap((edit): Turn[] => [
                  { role: "user", content: edit.message.slice(0, 6000) },
                  { role: "assistant", content: edit.summary },
                ]),
              });
        if (!active(n)) return false;
        const { timeline, pin, ...diff } = result;
        ++pinRequest;
        set({
          timeline,
          railTab: "ai",
          aiEdits: [
            ...aiEdits,
            {
              ...diff,
              message: "pin" in input ? input.pin.note : input.message,
            },
          ],
          ...(pin && {
            pins: get().pins.map((p) => (p.id === pin.id ? pin : p)),
          }),
        });
        return true;
      } catch (error) {
        if (active(n)) report(error);
        return false;
      } finally {
        if (active(n)) {
          set({ busy: false });
          void Promise.all([
            refreshTimeline(pid, n),
            refreshPins(pid, n),
          ]).catch(report);
        }
      }
    },
    undoAi: async (revision) => {
      if (get().timeline?.history_revision !== revision) return false;
      return change("undo");
    },
    railTab: "shots",
    setRailTab: (railTab) => set({ railTab }),
    setDraft: (pid, draft) => {
      if (get().project?.id === pid) set({ draft });
    },
    receiveMedia: (asset) => {
      if (get().project?.id === asset.project_id)
        set({
          media: [asset, ...get().media.filter((a) => a.id !== asset.id)],
        });
    },
    async refreshMedia(pid) {
      const media = await api.media(pid);
      if (get().project?.id === pid) set({ media });
    },
    modelCenter: null,
    showModels: (modelCenter) => set({ modelCenter }),
    acceptTimeline: (timeline) => {
      if (
        timeline.project_id === get().project?.id &&
        timeline.revision >= (get().timeline?.revision ?? 0)
      )
        set({ timeline });
    },
    projects: [],
    skills: [],
    project: null,
    timeline: null,
    media: [],
    pins: [],
    storage: null,
    stage: "plan",
    selection: null,
    busy: false,
    uploadProgress: null,
    delivery: idle,
    async refreshHome() {
      const [projects, skills] = await Promise.all([
        api.projects(),
        api.skills(),
      ]);
      set({ projects, skills });
      await get().refreshStorage();
    },
    async open(project) {
      get().close();
      const n = session,
        pid = project.id;
      set({ project });
      try {
        const { after, delivery } = await api.eventCursor(pid);
        const [timeline, media, pins] = await Promise.all([
          api.timeline(pid),
          api.media(pid),
          api.pins(pid),
        ]);
        if (!active(n)) return;
        set({ timeline, media, pins });
        if (delivery) receiveDelivery(delivery.stage_name, delivery.message);
        connect(pid, n, after);
        const url = new URL(location.href);
        url.searchParams.set("project", pid);
        history.replaceState(null, "", url);
      } catch (e) {
        if (active(n)) {
          get().close();
          report(e);
        }
      }
    },
    close() {
      session++;
      stream?.close();
      seenRevision = -1;
      set({
        aiEdits: [],
        draft: null,
        railTab: "shots",
        project: null,
        timeline: null,
        pins: [],
        media: [],
        selection: null,
        stage: "plan",
        busy: false,
        uploadProgress: null,
        delivery: idle,
      });
      const url = new URL(location.href);
      url.searchParams.delete("project");
      history.replaceState(null, "", url);
    },
    select: (selection) => set({ selection }),
    setStage: (stage) => set({ stage }),
    patchTimeline: (ops, summary) => change("patch", ops, summary),
    undo: () => change("undo"),
    redo: () => change("redo"),
    async addPin(data) {
      const n = session,
        pid = get().project!.id;
      try {
        const pin = await api.pin(pid, data);
        if (active(n)) {
          await refreshPins(pid, n);
          if (active(n)) {
            set({ selection: { pin: pin.id } });
            return pin;
          }
        }
      } catch (e) {
        report(e);
      }
    },
    async editPin(id, data) {
      const n = session,
        pid = get().project!.id;
      try {
        await api.editPin(pid, id, data);
        if (active(n)) await refreshPins(pid, n);
      } catch (e) {
        report(e);
      }
    },
    async deletePin(id) {
      const n = session,
        pid = get().project!.id;
      try {
        await api.deletePin(pid, id);
        if (active(n)) {
          const s = get().selection;
          if (s && "pin" in s && s.pin === id) set({ selection: null });
          await refreshPins(pid, n);
        }
      } catch (e) {
        report(e);
      }
    },
    async upload(file) {
      const n = session,
        pid = get().project!.id;
      if (get().uploadProgress !== null) {
        toast.info("已有素材正在上传");
        return;
      }
      set({ uploadProgress: 0 });
      try {
        const asset = await api.upload(pid, file, (p) => {
          if (active(n)) set({ uploadProgress: p });
        });
        if (active(n)) {
          set({ media: [asset, ...get().media] });
          void get().refreshStorage();
          return asset;
        }
      } catch (e) {
        report(e);
      } finally {
        if (active(n)) set({ uploadProgress: null });
      }
    },
    async refreshStorage() {
      try {
        set({ storage: await api.storage() });
      } catch (e) {
        report(e);
      }
    },
    async purge(scope) {
      const pid = get().project?.id,
        n = session;
      try {
        const r = await api.purge(pid, scope);
        await get().refreshStorage();
        if (pid && active(n)) {
          const media = await api.media(pid);
          if (active(n)) set({ media });
        }
        toast.success("已清理 " + (r.freed_bytes / 1048576).toFixed(1) + " MB");
      } catch (e) {
        report(e);
      }
    },
    async exportTimeline() {
      const n = session,
        doc = get().timeline;
      if (!doc || get().delivery.status === "rendering" || get().busy) return;
      set({ delivery: { status: "rendering" } });
      try {
        const result = await api.export(doc.project_id);
        if (active(n)) set({ delivery: { status: "done", result } });
        await get().refreshStorage();
      } catch (e) {
        if (active(n)) {
          set({
            delivery: {
              status: "error",
              message: e instanceof Error ? e.message : "导出失败",
            },
          });
          report(e);
        }
      }
    },
  };
});
