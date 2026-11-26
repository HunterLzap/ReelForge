import type { ReactNode } from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { ScreenFrame as Frame, Zoom, Clip } from "../types";

export function screenCamera(annotations: Clip[], frame: number, fps: number) {
  const ms = (frame * 1000) / fps;
  const focus = annotations
    .filter((c) => c.kind === "zoom_focus" && c.start_ms <= ms && ms < c.end_ms)
    .at(-1);
  if (!focus) return { scale: 1, x: 0, y: 0 };
  const target = focus.target_bbox ??
    focus.target_rect ??
    focus.rect ?? { x: 0.3, y: 0.3, w: 0.4, h: 0.4 };
  const local = Math.max(
    0,
    (Math.min(ms - focus.start_ms, focus.end_ms - ms) * fps) / 1000,
  );
  const amount = spring({
    fps,
    frame: local,
    config: { damping: 24, stiffness: 165, overshootClamping: true },
  });
  const full = focus.scale ?? focus.zoom_scale ?? 1.65;
  const pan = (center: number) =>
    amount * Math.max(1 - full, Math.min(0, 0.5 - center * full));
  return {
    scale: interpolate(amount, [0, 1], [1, full]),
    x: pan(target.x + target.w / 2),
    y: pan(target.y + target.h / 2),
  };
}
export type Camera = ReturnType<typeof screenCamera>;

export function ScreenFrame({
  style,
  zoom,
  children,
  camera,
  offset = 0,
}: {
  style?: Frame;
  zoom?: Zoom[];
  children: ReactNode;
  camera: Camera;
  offset?: number;
}) {
  const { fps } = useVideoConfig();
  const ms = (useCurrentFrame() * 1000) / fps + offset;
  const keys = [...(zoom || style?.zoom_keyframes || [])].sort(
    (a, b) => a[0] - b[0],
  );
  const unique = keys.filter((k, i) => i === 0 || k[0] !== keys[i - 1][0]);
  const at = (n: number, fallback: number) =>
    unique.length > 1
      ? interpolate(
          ms,
          unique.map((k) => k[0]),
          unique.map((k) => k[n]),
          {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: (t) => t * t * (3 - 2 * t),
          },
        )
      : (unique[0]?.[n] ?? fallback);
  return (
    <AbsoluteFill
      style={{
        transformOrigin: "top left",
        transform: `translate(${camera.x * 100}%, ${camera.y * 100}%) scale(${camera.scale})`,
        padding: style?.padding ?? (style ? 42 : 0),
        background:
          style?.gradient || "linear-gradient(140deg,#374852,#897a70)",
      }}
    >
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          overflow: "hidden",
          borderRadius:
            style?.borderRadius ??
            style?.border_radius ??
            (style && style.rounded !== false ? 28 : 0),
          boxShadow: style ? "0 22px 56px #07111788" : undefined,
        }}
      >
        <AbsoluteFill
          style={{
            transform: "scale(" + at(1, 1) + ")",
            transformOrigin: at(2, 0.5) * 100 + "% " + at(3, 0.5) * 100 + "%",
          }}
        >
          {children}
        </AbsoluteFill>
      </div>
    </AbsoluteFill>
  );
}
