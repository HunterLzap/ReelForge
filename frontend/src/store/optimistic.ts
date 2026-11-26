import type { Clip, TimelineDocument, TimelineOp } from "@/types";
import { tracks } from "@/studio";
function section(clip: Clip, start: number, end: number): Clip {
  const rate = clip.speed ?? 1,
    offset = clip.source_in_ms ?? 0;
  return {
    ...clip,
    start_ms: start,
    end_ms: end,
    source_in_ms: offset + Math.round((start - clip.start_ms) * rate),
    source_out_ms:
      end === clip.end_ms && clip.source_out_ms != null
        ? clip.source_out_ms
        : offset + Math.round((end - clip.start_ms) * rate),
  };
}
export function optimistic(doc: TimelineDocument, ops: TimelineOp[]) {
  const next = structuredClone(doc);
  for (const op of ops) {
    if (op.op === "set_bgm") next.bgm = op.bgm;
    else if (op.op === "set_subtitle_style")
      next.subtitle_style = op.subtitle_style;
    else if (op.op === "set_export_spec") {
      next.export = op.export;
      Object.assign(
        next,
        Object.fromEntries(
          Object.entries(op.export).filter(([k]) =>
            ["resolution", "aspect_ratio", "fps"].includes(k),
          ),
        ),
      );
    } else if (op.op === "ripple_delete") {
      const names = op.track === "all" ? tracks : [op.track];
      const target = names
        .flatMap((t) => next.tracks[t])
        .find((c) => c.id === op.clip_id);
      if (!target) continue;
      const { start_ms: a, end_ms: b } = target;
      for (const t of names)
        next.tracks[t] = next.tracks[t].flatMap((c) => {
          const parts: Clip[] = [];
          if (c.start_ms < a)
            parts.push(c.end_ms <= a ? c : section(c, c.start_ms, a));
          if (c.end_ms > b) {
            const tail = c.start_ms < b ? section(c, b, c.end_ms) : { ...c };
            if (c.start_ms < a) tail.id = crypto.randomUUID();
            tail.start_ms -= b - a;
            tail.end_ms -= b - a;
            parts.push(tail);
          }
          return parts;
        });
    } else {
      const items = next.tracks[op.track];
      if (op.op === "add_clip") {
        items.push(op.clip);
        items.sort((a, b) => a.start_ms - b.start_ms);
        continue;
      }
      const index = items.findIndex((c) => c.id === op.clip_id);
      if (index < 0) continue;
      const c = items[index];
      if (op.op === "delete_clip") items.splice(index, 1);
      else if (op.op === "update_clip") {
        items[index] = { ...c, ...op.patch };
        if (op.patch.props)
          items[index].props = { ...c.props, ...op.patch.props };
      } else if (
        op.op === "split_clip" &&
        c.start_ms < op.at_ms &&
        op.at_ms < c.end_ms
      )
        items.splice(index, 1, section(c, c.start_ms, op.at_ms), {
          ...section(c, op.at_ms, c.end_ms),
          id: crypto.randomUUID(),
        });
    }
  }
  return next;
}
