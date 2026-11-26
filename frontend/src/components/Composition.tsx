import { useMemo } from "react";
import { TimelinePlayer } from "@motion/TimelinePlayer";
import { durationMs, frames } from "@motion/types";
import { api, resourceUrl } from "@/api/client";
import type { TimelineDocument } from "@/types";
export function useComposition(doc: TimelineDocument) {
  return useMemo(() => {
    const timeline = structuredClone(doc);
    const local = (src: string) =>
      resourceUrl(
        /^(?:media|assets|scenes|proxies)\//.test(src)
          ? "/workspace/" + doc.project_id + "/" + src
          : src,
      );
    for (const clip of [
      ...Object.values(timeline.tracks).flat(),
      timeline.bgm,
    ]) {
      if (clip?.src) clip.src = local(clip.src);
      if (clip?.props?.src) clip.props.src = local(clip.props.src);
    }
    return {
      component: TimelinePlayer,
      inputProps: { timeline, resolveAsset: api.stream },
      fps: doc.fps,
      durationInFrames: Math.max(1, frames(durationMs(doc), doc.fps)),
      compositionWidth: doc.resolution.width,
      compositionHeight: doc.resolution.height,
    };
  }, [doc]);
}
