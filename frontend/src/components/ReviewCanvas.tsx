import { useRef, useState, type RefObject, type PointerEvent } from "react";
import { toPng } from "html-to-image";
import { useStudio } from "@/store/studioStore";
import type { Rect, PinCreate } from "@/types";
import type { PlayerHandle } from "./editorPlayback";
import { usePlayback } from "./editorPlayback";
import { Button } from "./ui/button";
type Point = { x: number; y: number };
function point(e: PointerEvent<HTMLElement>): Point {
  const b = e.currentTarget.getBoundingClientRect();
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  return {
    x: clamp((e.clientX - b.left) / b.width),
    y: clamp((e.clientY - b.top) / b.height),
  };
}
function rect(a: Point, b: Point): Rect {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(a.x - b.x),
    h: Math.abs(a.y - b.y),
  };
}
const position = (b: Rect) => ({
  left: b.x * 100 + "%",
  top: b.y * 100 + "%",
  width: b.w * 100 + "%",
  height: b.h * 100 + "%",
});
export function ReviewCanvas({
  mode,
  exit,
  source,
  player,
  jump,
}: {
  mode: boolean;
  exit: () => void;
  source: RefObject<HTMLDivElement | null>;
  player: PlayerHandle;
  jump: (ms: number) => void;
}) {
  const { timeline: doc, pins, select, addPin, selection } = useStudio();
  const frame = usePlayback((s) => s.frame);
  const origin = useRef<Point | null>(null);
  const [box, draw] = useState<Rect | null>(null),
    [pending, noteAt] = useState<Omit<PinCreate, "note"> | null>(null),
    [note, setNote] = useState(""),
    [busy, save] = useState(false);
  const capture = useRef<Promise<string | undefined> | null>(null);
  if (!doc) return null;
  const ms = Math.round((frame * 1000) / doc.fps);
  function finish(e: PointerEvent<HTMLDivElement>) {
    if (!origin.current || !doc) return;
    const bbox = rect(origin.current, point(e));
    origin.current = null;
    if (bbox.w < 0.008 || bbox.h < 0.008) {
      draw(null);
      return;
    }
    const time_ms = Math.round(
      ((player.current?.getCurrentFrame() ?? frame) * 1000) / doc.fps,
    );
    const target = selection && "id" in selection ? selection : null;
    draw(bbox);
    setNote("");
    noteAt({
      bbox,
      time_ms,
      revision: doc.revision,
      track: target?.track,
      clip_id: target?.id,
    });
    // The backend renders this exact revision and frame if browser capture is unavailable.
    capture.current = source.current
      ? toPng(source.current, { pixelRatio: 1, skipFonts: true }).catch(
          () => undefined,
        )
      : null;
  }
  return (
    <>
      <div
        className={"review-canvas " + (mode ? "drawing" : "")}
        onPointerDown={(e) => {
          if (!mode || pending || e.button !== 0) return;
          player.current?.pause();
          origin.current = point(e);
          draw(null);
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (origin.current) draw(rect(origin.current, point(e)));
        }}
        onPointerUp={finish}
        onPointerCancel={() => {
          origin.current = null;
          draw(null);
        }}
      >
        {pins.map((p, i) => {
          if (Math.abs(p.time_ms - ms) > Math.max(500, 1000 / doc.fps))
            return null;
          const b = p.bbox ?? { x: 0.04, y: 0.04, w: 0.05, h: 0.05 };
          return (
            <div
              className={
                "pin-box " + (p.status === "resolved" ? "resolved" : "")
              }
              key={p.id}
              style={position(b)}
            >
              <button
                title={p.note}
                aria-label={"图钉 " + (i + 1)}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => {
                  select({ pin: p.id });
                  jump(p.time_ms);
                }}
              >
                {i + 1}
              </button>
            </div>
          );
        })}
        {mode && box && <div className="draft-box" style={position(box)} />}
      </div>
      {mode && pending && (
        <form
          className="note-popover stack"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!note.trim() || busy) return;
            save(true);
            const pin = await addPin({
              ...pending,
              note: note.trim(),
              frame_data_url: (await capture.current) ?? undefined,
            });
            save(false);
            if (pin) exit();
          }}
        >
          <label className="field">
            画框批注
            <textarea
              autoFocus
              maxLength={8000}
              placeholder="写下此处需要调整的内容"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="row">
            <Button onClick={exit} disabled={busy}>
              取消
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={!note.trim() || busy}
            >
              {busy ? "正在保存…" : "保存批注"}
            </Button>
          </div>
        </form>
      )}
    </>
  );
}
