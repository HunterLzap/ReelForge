import { useEffect, useRef, useState } from "react";
import {
  DndContext,
  PointerSensor,
  useDraggable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import WaveSurfer from "wavesurfer.js";
import {
  Scissors,
  Trash2,
  Plus,
  Minus,
  Maximize,
  Film,
  Layers,
  Focus,
  Captions,
  Music2,
} from "lucide-react";
import { api, resourceUrl } from "@/api/client";
import { useStudio } from "@/store/studioStore";
import { usePlayback, useShortcut } from "./editorPlayback";
import { Button } from "./ui/button";
import {
  clipName,
  endOf,
  makeCard,
  tracks,
  trackLabels,
  timecode,
} from "@/studio";
import type { TrackName, Clip } from "@/types";
const icons = {
  video: Film,
  overlay: Layers,
  annotation: Focus,
  subtitle: Captions,
  audio: Music2,
};
function Waveform({ src }: { src: string }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current) return;
    const wave = WaveSurfer.create({
      container: el.current,
      height: 24,
      interact: false,
      cursorWidth: 0,
      waveColor: "#67bca3",
      progressColor: "#67bca3",
      normalize: true,
      barWidth: 2,
    });
    const off = wave.on("error", () => {});
    void wave.load(src).catch(() => {});
    return () => {
      off();
      wave.destroy();
    };
  }, [src]);
  return <div className="waveform" aria-hidden ref={el} />;
}
type Part = "left" | "move" | "right";
function dragData(c: Clip, track: TrackName, part: Part) {
  return { id: c.id + "-" + part, data: { clip: c, track, part } };
}
function Block({
  c,
  track,
  span,
  selected,
  choose,
  unit,
}: {
  c: Clip;
  track: TrackName;
  span: number;
  selected: boolean;
  choose: () => void;
  unit: number;
}) {
  const move = useDraggable(dragData(c, track, "move")),
    left = useDraggable(dragData(c, track, "left")),
    right = useDraggable(dragData(c, track, "right"));
  const px = move.transform?.x ?? left.transform?.x ?? right.transform?.x ?? 0;
  let a = c.start_ms,
    b = c.end_ms;
  if (move.isDragging) {
    a = Math.max(0, a + px * unit);
    b = a + c.end_ms - c.start_ms;
  }
  if (left.isDragging) a = Math.max(0, Math.min(b - 1, a + px * unit));
  if (right.isDragging) b = Math.max(a + 1, b + px * unit);
  const src = c.src
    ? resourceUrl(c.src)
    : c.asset_id
      ? api.stream(c.asset_id)
      : undefined;
  return (
    <div
      className={
        "clip " +
        (selected ? "active " : "") +
        (c.source_state === "placeholder" || c.kind === "placeholder"
          ? "placeholder"
          : "")
      }
      style={{
        left: (a / span) * 100 + "%",
        width: ((b - a) / span) * 100 + "%",
      }}
      title={clipName(c)}
    >
      {track === "audio" && src && <Waveform src={src} />}
      <button
        ref={move.setNodeRef}
        {...move.listeners}
        {...move.attributes}
        className="clip-move"
        onClick={choose}
      >
        {clipName(c)}
      </button>
      <span
        ref={left.setNodeRef}
        {...left.listeners}
        className="trim left"
        title="修剪入点"
      />
      <span
        ref={right.setNodeRef}
        {...right.listeners}
        className="trim right"
        title="修剪出点"
      />
    </div>
  );
}
export function TimelinePanel({
  jump,
  shortcuts,
}: {
  jump: (ms: number) => void;
  shortcuts: boolean;
}) {
  const {
    timeline: doc,
    selection,
    select,
    patchTimeline,
    pins,
    media,
  } = useStudio();
  const frame = usePlayback((s) => s.frame);
  const [zoom, setZoom] = useState(1),
    [width, setWidth] = useState(800);
  const ruler = useRef<HTMLDivElement>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );
  useEffect(() => {
    const el = ruler.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const duration = doc ? endOf(doc) : 0,
    ms = doc ? Math.round((frame * 1000) / doc.fps) : 0,
    span = Math.max(duration, 1000) / Math.min(1, zoom);
  const unit = span / Math.max(1, width);
  const selected =
    doc && selection && "id" in selection
      ? doc.tracks[selection.track].find((c) => c.id === selection.id)
      : undefined;
  const splittable = selected && selected.start_ms < ms && ms < selected.end_ms;
  function split() {
    if (splittable && selection && "id" in selection)
      void patchTimeline(
        [
          {
            op: "split_clip",
            track: selection.track,
            clip_id: selection.id,
            at_ms: ms,
          },
        ],
        "分割片段",
      );
  }
  function remove() {
    if (selected && selection && "id" in selection)
      void patchTimeline(
        [
          {
            op: "ripple_delete",
            track: selection.track === "video" ? "all" : selection.track,
            clip_id: selection.id,
          },
        ],
        "波纹删除片段",
      );
  }
  useShortcut("s", split, shortcuts);
  useShortcut("delete,backspace", remove, shortcuts);
  if (!doc) return null;
  function drag(e: DragEndEvent) {
    const {
      clip: c,
      track,
      part,
    } = e.active.data.current as { clip: Clip; track: TrackName; part: Part };
    const d = Math.round(e.delta.x * unit);
    if (!d) return;
    let a = c.start_ms,
      b = c.end_ms;
    const patch: Partial<Clip> = {};
    if (part === "move") {
      a = Math.max(0, a + d);
      b = a + c.end_ms - c.start_ms;
    } else if (part === "left") {
      const source = c.source_in_ms ?? 0,
        speed = c.speed ?? 1;
      a = Math.max(0, Math.min(b - 1, a + d));
      if (c.asset_id || c.src) {
        a = Math.max(a, c.start_ms - Math.floor(source / speed));
        patch.source_in_ms = source + Math.round((a - c.start_ms) * speed);
      }
    } else {
      b = Math.max(a + 1, b + d);
      if (c.asset_id || c.src) {
        const offset = c.source_in_ms ?? 0,
          speed = c.speed ?? 1;
        const sourceLength = media.find(
          (asset) => asset.id === c.asset_id,
        )?.duration_ms;
        if (sourceLength && sourceLength > offset)
          b = Math.min(
            b,
            a + Math.max(1, Math.floor((sourceLength - offset) / speed)),
          );
        patch.source_out_ms = offset + Math.max(1, Math.round((b - a) * speed));
      }
    }
    select({ track, id: c.id });
    void patchTimeline(
      [
        {
          op: "update_clip",
          track,
          clip_id: c.id,
          patch: { ...patch, start_ms: a, end_ms: b },
        },
      ],
      part === "move" ? "移动片段" : "修剪片段",
    );
  }
  const step = Math.max(
    1,
    10 ** Math.floor(Math.log10(span / Math.max(2, width / 85))),
  );
  const tick =
    [1, 2, 5, 10].map((n) => n * step).find((t) => t / unit >= 70) ?? step * 10;
  const scrub = (e: React.PointerEvent<HTMLDivElement>) => {
    const bounds = e.currentTarget.getBoundingClientRect();
    jump(Math.max(0, Math.min(duration, (e.clientX - bounds.left) * unit)));
  };
  return (
    <section className="timeline">
      <div className="timeline-toolbar">
        <h2>时间轴</h2>
        <Button disabled={!splittable} onClick={split}>
          <Scissors />
          分割 S
        </Button>
        <Button disabled={!selected} onClick={remove}>
          <Trash2 />
          波纹删除 Del
        </Button>
        <Button
          onClick={() =>
            patchTimeline(
              [
                {
                  op: "add_clip",
                  track: "video",
                  clip: makeCard(
                    Math.max(0, ...doc.tracks.video.map((c) => c.end_ms)),
                    "新动效卡",
                  ),
                },
              ],
              "添加动效卡",
            )
          }
        >
          <Plus />
          添加动效卡
        </Button>
        <div className="zoom">
          <Button
            aria-label="缩小"
            disabled={zoom <= 0.25}
            onClick={() => setZoom(Math.max(0.25, zoom / 1.5))}
          >
            <Minus />
          </Button>
          <Button
            aria-label="放大"
            disabled={zoom >= 8}
            onClick={() => setZoom(Math.min(8, zoom * 1.5))}
          >
            <Plus />
          </Button>
          <Button onClick={() => setZoom(1)}>
            <Maximize />
            适配
          </Button>
        </div>
      </div>
      <div className="timeline-scroll">
        <div
          className="timeline-grid"
          style={{ width: Math.max(1, zoom) * 100 + "%" }}
        >
          <div className="track-name ruler-name">时间</div>
          <div
            ref={ruler}
            className="ruler"
            onPointerDown={(e) => {
              e.currentTarget.setPointerCapture(e.pointerId);
              scrub(e);
            }}
            onPointerMove={(e) => {
              if (e.buttons === 1) scrub(e);
            }}
          >
            {Array.from({ length: Math.ceil(span / tick) }, (_, i) => (
              <time key={i} style={{ left: ((i * tick) / span) * 100 + "%" }}>
                {timecode(i * tick)}
              </time>
            ))}
            {pins.map((p, i) => (
              <button
                key={p.id}
                className="ruler-pin"
                style={{ left: Math.min(99, (p.time_ms / span) * 100) + "%" }}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => {
                  select({ pin: p.id });
                  jump(p.time_ms);
                }}
                title={p.note}
              >
                {i + 1}
              </button>
            ))}
          </div>
          <DndContext
            sensors={sensors}
            onDragStart={(e) => {
              const { clip, track } = e.active.data.current!;
              select({ track, id: clip.id });
            }}
            onDragEnd={drag}
          >
            {tracks.map((t) => {
              const Icon = icons[t];
              return (
                <div className="track-row" key={t} data-track={t}>
                  <div className="track-name">
                    <Icon />
                    {trackLabels[t]}
                  </div>
                  <div
                    className="lane"
                    onClick={(e) => {
                      if (e.target === e.currentTarget) {
                        select(null);
                        jump(
                          (e.clientX -
                            e.currentTarget.getBoundingClientRect().left) *
                            unit,
                        );
                      }
                    }}
                  >
                    {t === "audio" && doc.bgm && (
                      <div
                        className="bed"
                        style={{ width: (duration / span) * 100 + "%" }}
                      >
                        {(doc.bgm.src || doc.bgm.asset_id) && (
                          <Waveform
                            src={
                              doc.bgm.src
                                ? resourceUrl(doc.bgm.src)
                                : api.stream(doc.bgm.asset_id!)
                            }
                          />
                        )}
                        背景音乐
                      </div>
                    )}
                    {doc.tracks[t].map((c) => (
                      <Block
                        key={c.id}
                        c={c}
                        track={t}
                        unit={unit}
                        span={span}
                        selected={selected?.id === c.id}
                        choose={() => {
                          select({ track: t, id: c.id });
                          jump(c.start_ms);
                        }}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </DndContext>
          <div className="head-area">
            <div
              className="playhead"
              style={{ left: Math.min(100, (ms / span) * 100) + "%" }}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
