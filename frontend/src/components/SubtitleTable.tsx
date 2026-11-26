import { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useStudio, report } from "@/store/studioStore";
import { timecode } from "@/studio";
import type { Clip, TimelineOp } from "@/types";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

function CaptionRow({
  clip: c,
  next,
  index,
  jump,
}: {
  clip: Clip;
  next?: Clip;
  index: number;
  jump: (ms: number) => void;
}) {
  const patch = useStudio((s) => s.patchTimeline),
    [draft, edit] = useState(c.text ?? ""),
    caret = useRef<number | null>(null);
  useEffect(() => edit(c.text ?? ""), [c.text]);
  const change = (patch: Partial<Clip>): TimelineOp => ({
    op: "update_clip",
    track: "subtitle",
    clip_id: c.id,
    patch,
  });
  const remove = (clip_id: string): TimelineOp => ({
    op: "delete_clip",
    track: "subtitle",
    clip_id,
  });
  const commit = () => {
    if (draft !== c.text) void patch([change({ text: draft })], "校正字幕");
  };
  function split() {
    const chars = Array.from(draft);
    if (chars.length < 2 || c.end_ms - c.start_ms < 2) return;
    const cursor = Array.from(draft.slice(0, caret.current ?? 0)).length;
    const n =
      cursor > 0 && cursor < chars.length
        ? cursor
        : Math.ceil(chars.length / 2);
    const at = Math.max(
      c.start_ms + 1,
      Math.min(
        c.end_ms - 1,
        c.start_ms + Math.round(((c.end_ms - c.start_ms) * n) / chars.length),
      ),
    );
    const id = crypto.randomUUID();
    void patch(
      [
        change({ text: chars.slice(0, n).join(""), end_ms: at }),
        {
          op: "add_clip",
          track: "subtitle",
          clip: {
            ...c,
            id,
            start_ms: at,
            end_ms: c.end_ms,
            text: chars.slice(n).join(""),
            transcript_segment_id: c.transcript_segment_id ? id : undefined,
          },
        },
      ],
      "拆分字幕",
    );
  }
  const merge = () => {
    if (next)
      void patch(
        [
          change({
            text: draft + (next.text ?? ""),
            end_ms: Math.max(c.end_ms, next.end_ms),
          }),
          remove(next.id),
        ],
        "合并相邻字幕",
      );
  };
  return (
    <div role="row" className="caption-row" onClick={() => jump(c.start_ms)}>
      <span>{index + 1}</span>
      <time>
        {timecode(c.start_ms)} – {timecode(c.end_ms)}
      </time>
      <Input
        aria-label={`第 ${index + 1} 行字幕`}
        value={draft}
        className={draft.length > 42 ? "long-caption" : ""}
        onSelect={(e) => (caret.current = e.currentTarget.selectionStart)}
        onChange={(e) => edit(e.target.value)}
        onKeyDown={(e) => {
          if (e.nativeEvent.isComposing) return;
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
          if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "m") {
            e.preventDefault();
            merge();
          }
        }}
      />
      <div className="row">
        <Button disabled={draft.length < 2} onClick={split}>
          拆分
        </Button>
        <Button disabled={!next} onClick={merge}>
          合并
        </Button>
        <Button
          aria-label="删除字幕"
          onClick={() => patch([remove(c.id)], "删除字幕")}
        >
          <Trash2 />
        </Button>
      </div>
    </div>
  );
}

export function SubtitleTable({ jump }: { jump: (ms: number) => void }) {
  const doc = useStudio((s) => s.timeline)!,
    accept = useStudio((s) => s.acceptTimeline);
  const rows = useMemo(
    () => [...doc.tracks.subtitle].sort((a, b) => a.start_ms - b.start_ms),
    [doc.tracks.subtitle],
  );
  const parent = useRef<HTMLDivElement>(null),
    [find, term] = useState(""),
    [replace, replacement] = useState("");
  const virtual = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parent.current,
    estimateSize: () => 44,
    overscan: 6,
    getItemKey: (i) => rows[i].id,
  });
  async function glossary() {
    try {
      const res = await api.replaceTerms(
        doc.project_id,
        doc.revision,
        find,
        replace,
      );
      accept(res.timeline);
      toast.success(`已替换 ${res.replaced_count} 处`);
    } catch (e) {
      report(e);
    }
  }
  return (
    <section className="subtitle-table">
      <div className="subtitle-tools row">
        <Input
          placeholder="查找术语"
          aria-label="查找术语"
          value={find}
          onChange={(e) => term(e.target.value)}
        />
        <Input
          placeholder="替换为"
          aria-label="替换为"
          value={replace}
          onChange={(e) => replacement(e.target.value)}
        />
        <Button disabled={!find} onClick={glossary}>
          批量替换
        </Button>
        {(["srt", "ass"] as const).map((f) => (
          <a
            className="btn"
            key={f}
            download
            href={api.subtitlesUrl(doc.project_id, f)}
          >
            导出 {f.toUpperCase()}
          </a>
        ))}
      </div>
      <div className="caption-header caption-row">
        {["#", "入点 / 出点", "字幕文本", "操作"].map((v) => (
          <strong key={v}>{v}</strong>
        ))}
      </div>
      <div className="caption-scroll" ref={parent}>
        {!rows.length && (
          <p className="empty">在文稿中生成字幕后可逐行校对。</p>
        )}
        <div
          role="table"
          aria-label="极速字幕"
          style={{ height: virtual.getTotalSize(), position: "relative" }}
        >
          {virtual.getVirtualItems().map((item) => (
            <div
              key={item.key}
              style={{
                position: "absolute",
                width: "100%",
                top: 0,
                transform: `translateY(${item.start}px)`,
              }}
            >
              <CaptionRow
                index={item.index}
                clip={rows[item.index]}
                next={rows[item.index + 1]}
                jump={jump}
              />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
