import { useEffect } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { report, useStudio } from "@/store/studioStore";
import type { PasteInput } from "@/types";

export function useMaterialPaste(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    async function paste(e: ClipboardEvent) {
      if (
        e.target instanceof Element &&
        e.target.closest(
          'input,textarea,[contenteditable="true"],[role="textbox"]',
        )
      )
        return;
      const { timeline, selection, receiveMedia, acceptTimeline } =
        useStudio.getState();
      if (!timeline || !e.clipboardData) return;
      const file = Array.from(e.clipboardData.items)
        .find((i) => /^image\/(png|jpeg|webp)$/.test(i.type))
        ?.getAsFile();
      const url = e.clipboardData.getData("text/plain").trim();
      if (!file && !/^https?:\/\/\S+$/i.test(url)) return;
      e.preventDefault();
      const body: PasteInput = {};
      if (
        selection &&
        "track" in selection &&
        timeline.tracks[selection.track].some(
          (c) => c.id === selection.id && c.kind === "placeholder",
        )
      )
        Object.assign(body, {
          slot_clip_id: selection.id,
          track: selection.track,
          base_revision: timeline.revision,
        });
      try {
        if (file) {
          body.filename = file.name;
          body.image_data_url = await new Promise<string>((resolve, reject) => {
            const r = new FileReader();
            r.onload = () => resolve(String(r.result));
            r.onerror = () => reject(r.error);
            r.readAsDataURL(file);
          });
        } else body.url = url;
        const r = await api.paste(timeline.project_id, body);
        receiveMedia(r.asset);
        if (r.timeline) acceptTimeline(r.timeline);
        toast.success(r.timeline ? "已替换占位镜头" : "已加入工程素材");
      } catch (error) {
        report(error);
      }
    }
    document.addEventListener("paste", paste);
    return () => document.removeEventListener("paste", paste);
  }, [enabled]);
}
