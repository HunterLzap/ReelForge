import type { ReactNode } from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { ScreenFrame as Frame, Zoom } from "../types";

export function ScreenFrame({
  style,
  zoom,
  children,
  offset = 0,
}: {
  style?: Frame;
  zoom?: Zoom[];
  children: ReactNode;
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
