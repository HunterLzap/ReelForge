import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { EditorialCard } from "../../../skills/motion-editorial/components/EditorialCard";
import type { Clip, SubtitleStyle } from "../types";

export function Overlay({ clip, src }: { clip: Clip; src?: string }) {
  const f = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const enter = spring({ frame: f, fps, config: { damping: 20 } });
  const r = clip.rect ||
    clip.target_rect || { x: 0.06, y: 0.09, w: 0.5, h: 0.12 };
  const spotlight =
    clip.spotlight || ["spotlight", "zoom_focus"].includes(clip.kind);
  const cursor = ["cursor", "cursor_focus"].includes(clip.kind);
  const label =
    clip.callout_text || clip.text || clip.props?.text || clip.props?.title;
  return (
    <div
      style={{
        position: "absolute",
        left: r.x * width,
        top: r.y * height,
        width: r.w * width,
        height: r.h * height,
        opacity: enter,
        transform: "translateY(" + (1 - enter) * 18 + "px)",
        borderRadius: clip.border_radius ?? 16,
        boxShadow: spotlight ? "0 0 0 300vmax rgba(0,0,0,.55)" : undefined,
        border: spotlight ? "4px solid #f4d199" : undefined,
        background: spotlight || cursor || src ? "transparent" : "#16282eef",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff8ee",
        fontSize: Math.min(width, height) * 0.039,
        fontWeight: 650,
        textAlign: "center",
      }}
    >
      {clip.kind === "motion_card" || clip.component_id ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            overflow: "hidden",
            borderRadius: "inherit",
          }}
        >
          <div
            style={{
              position: "absolute",
              width,
              height,
              transformOrigin: "top left",
              transform: "scale(" + r.w + "," + r.h + ")",
            }}
          >
            <EditorialCard
              template={clip.component_id || "cover"}
              content={clip.props || {}}
            />
          </div>
        </div>
      ) : (
        src &&
        (["broll_video", "video_clip", "video"].includes(clip.kind) ? (
          <OffthreadVideo
            src={src}
            trimBefore={Math.round(((clip.source_in_ms || 0) * fps) / 1000)}
            playbackRate={clip.speed || 1}
            volume={clip.volume ?? 0}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <Img
            src={src}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              borderRadius: "inherit",
            }}
          />
        ))
      )}

      {cursor && (
        <div
          style={{
            width: 34,
            height: 34,
            border: "4px solid white",
            borderRadius: "50%",
            background: "#ddaa47",
            boxShadow: "0 0 0 15px #e9bd8355",
          }}
        />
      )}
      {label && !clip.component_id && clip.kind !== "motion_card" && (
        <span
          style={{
            position: spotlight ? "absolute" : undefined,
            top: "102%",
            background: spotlight ? "#23353c" : undefined,
            padding: 12,
            borderRadius: 8,
          }}
        >
          {label}
        </span>
      )}
    </div>
  );
}
export function Caption({ clip, style }: { clip: Clip; style: SubtitleStyle }) {
  const { width, height } = useVideoConfig();
  const custom = typeof style === "string" ? {} : style;
  const preset =
    clip.style_preset || (typeof style === "string" ? style : style.preset);
  const bar = preset === "highlight_bar",
    stroke = preset === "clean_stroke" || preset === "clean_caption";
  const highlighted = clip.highlight_words?.filter(Boolean) || [];
  const words = highlighted.length
    ? (clip.text || "").split(
        new RegExp(
          "(" +
            highlighted
              .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
              .join("|") +
            ")",
          "g",
        ),
      )
    : [clip.text];
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom:
          clip.caption_bottom !== undefined
            ? height * clip.caption_bottom
            : (custom.bottom ?? height * 0.065),
        paddingInline: width * 0.06,
      }}
    >
      <div
        style={{
          borderRadius: 16,
          padding: "0.22em 0.65em",
          fontSize: custom.font_size || Math.min(width, height) * 0.045,
          fontWeight: 700,
          textAlign: "center",
          color: custom.color || (bar ? "#151515" : "white"),
          textShadow: stroke ? "0 2px 5px black, 2px 0 3px black" : undefined,
          background:
            custom.background ||
            (bar ? "#f1c483" : stroke ? "transparent" : "#131b20d9"),
        }}
      >
        {words.map((word, i) => (
          <span
            key={i}
            style={{
              color: word && highlighted.includes(word) ? "#eab766" : undefined,
            }}
          >
            {word}
          </span>
        ))}
      </div>
    </AbsoluteFill>
  );
}
export function PlaceholderCard({ clip }: { clip: Clip }) {
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        background: "#27353e",
        color: "#eadcc4",
        fontSize: 54,
        padding: "9%",
        textAlign: "center",
      }}
    >
      {clip.prompt_hint || clip.text || "待补充素材"}
    </AbsoluteFill>
  );
}
