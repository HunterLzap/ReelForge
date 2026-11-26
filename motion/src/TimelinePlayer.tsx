import type { CSSProperties } from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  staticFile,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  NewsCard,
  isNewsTemplate,
} from "../../skills/ai-news-montage/components/NewsCard";
import { EditorialCard } from "../../skills/motion-editorial/components/EditorialCard";
import { Caption, Overlay, PlaceholderCard } from "./components/Layers";
import { ScreenFrame, screenCamera } from "./components/ScreenFrame";
import { durationMs, frames } from "./types";
import type { Clip, TimelineDocument, TrackName } from "./types";

const mediaUrl = (url?: string) =>
  url?.startsWith("staged:") ? staticFile(url.slice(7)) : url;

export interface PlayerProps extends Record<string, unknown> {
  timeline: TimelineDocument;
  resolveAsset?: (assetId: string) => string;
}
function Visual({
  clip,
  src,
  theme,
  annotations,
}: {
  clip: Clip;
  src?: string;
  theme?: string;
  annotations: Clip[];
}) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const camera = screenCamera(annotations, f + frames(clip.start_ms, fps), fps);
  const ms = (f * 1000) / fps;
  const duration = clip.end_ms - clip.start_ms;
  const fade =
    clip.transition_out?.type === "fade" ? clip.transition_out.duration_ms : 0;
  const opacity =
    fade > 0
      ? interpolate(ms, [duration - fade, duration], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;
  const offset = frames(clip.source_in_ms || 0, fps);
  const mediaStyle: CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: clip.crop?.mode || "cover",
    objectPosition:
      (clip.crop?.focus_x ?? 0.5) * 100 +
      "% " +
      (clip.crop?.focus_y ?? 0.5) * 100 +
      "%",
  };
  let content;
  if (clip.kind === "placeholder" || clip.source_state === "placeholder")
    content = <PlaceholderCard clip={clip} />;
  else if (isNewsTemplate(clip.component_id || clip.kind))
    content = (
      <Sequence from={-offset}>
        <NewsCard
          template={clip.component_id || clip.kind}
          content={{ ...clip.props, src: src || mediaUrl(clip.props?.src) }}
          video={
            clip.props?.media_type === "video" || clip.kind === "video_clip"
          }
        />
      </Sequence>
    );
  else if (clip.kind === "motion_card")
    content = (
      <Sequence from={-offset}>
        <EditorialCard
          theme={theme}
          template={
            clip.component_id || clip.template_id || clip.template || "cover"
          }
          content={{ ...clip.props, src: mediaUrl(clip.props?.src) }}
        />
      </Sequence>
    );
  else if (!src) content = <PlaceholderCard clip={clip} />;
  else if (["image_clip", "image"].includes(clip.kind))
    content = (
      <Img
        src={src}
        style={{
          ...mediaStyle,
          transform: "scale(" + (1 + (0.035 * ms) / duration) + ")",
        }}
      />
    );
  else
    content = (
      <OffthreadVideo
        src={src}
        trimBefore={offset}
        trimAfter={
          clip.source_out_ms ? frames(clip.source_out_ms, fps) : undefined
        }
        playbackRate={clip.speed || 1}
        volume={clip.volume ?? 1}
        style={mediaStyle}
      />
    );
  return (
    <AbsoluteFill style={{ opacity }}>
      <ScreenFrame
        camera={camera}
        style={clip.screen_frame || clip.frame_style}
        zoom={clip.zoom_keyframes}
        offset={clip.source_in_ms}
      >
        {content}
      </ScreenFrame>
    </AbsoluteFill>
  );
}
function Sound({
  clip,
  src,
  voices,
  loop,
}: {
  clip: Clip;
  src: string;
  voices: Clip[];
  loop?: boolean;
}) {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const local = (frame * 1000) / fps;
  const time = clip.start_ms + local;
  const ramp = (v: number, d: number) =>
    d > 0 ? Math.max(0, Math.min(1, v / d)) : 1;
  const duck = voices.reduce(
    (v, c) =>
      Math.max(
        v,
        Math.min(
          ramp(time - c.start_ms + 150, 150),
          ramp(c.end_ms - time + 250, 250),
        ),
      ),
    0,
  );
  const bed = clip.kind === "bgm";
  const volume =
    (clip.volume ?? (bed ? 0.35 : 1)) *
    ramp(local, clip.fade_in_ms || 0) *
    ramp(clip.end_ms - time, clip.fade_out_ms || 0) *
    (bed ? 1 - duck * (1 - Math.pow(10, (clip.ducking_db ?? -10) / 20)) : 1);
  return (
    <Audio
      src={src}
      trimBefore={frames(clip.source_in_ms || 0, fps)}
      trimAfter={
        clip.source_out_ms ? frames(clip.source_out_ms, fps) : undefined
      }
      playbackRate={clip.speed || 1}
      volume={volume}
      loop={loop}
    />
  );
}
export function TimelinePlayer({ timeline: doc, resolveAsset }: PlayerProps) {
  const { fps } = useVideoConfig();
  const source = (c: Clip) =>
    mediaUrl(c.src) ||
    (c.asset_id
      ? resolveAsset?.(c.asset_id) ||
        "/api/media/" + encodeURIComponent(c.asset_id) + "/stream?variant=proxy"
      : undefined);
  const voices = [
    ...doc.tracks.audio.filter((c) => c.kind !== "bgm"),
    ...doc.tracks.video.filter(
      (c) => ["video_clip", "video"].includes(c.kind) && c.volume !== 0,
    ),
  ];
  const tracks = { ...doc.tracks };
  if (doc.bgm)
    tracks.audio = [
      ...tracks.audio,
      {
        id: "bgm",
        start_ms: 0,
        end_ms: durationMs(doc),
        ...doc.bgm,
        kind: "bgm",
      },
    ];
  return (
    <AbsoluteFill
      style={{
        background: "#111a20",
        fontFamily: "Inter, PingFang SC, sans-serif",
        overflow: "hidden",
      }}
    >
      {(
        ["video", "overlay", "annotation", "subtitle", "audio"] as TrackName[]
      ).map((track) =>
        tracks[track].map((clip) => {
          const src = source(clip);
          const from = frames(clip.start_ms, fps);
          return (
            <Sequence
              key={track + clip.id}
              from={from}
              durationInFrames={Math.max(1, frames(clip.end_ms, fps) - from)}
            >
              {track === "video" ? (
                <Visual
                  annotations={doc.tracks.annotation}
                  clip={clip}
                  src={src}
                  theme={doc.theme}
                />
              ) : track === "subtitle" ? (
                <Caption clip={clip} style={doc.subtitle_style} />
              ) : track === "audio" ? (
                src && (
                  <Sound
                    clip={clip}
                    src={src}
                    voices={voices}
                    loop={clip.kind === "bgm" && doc.bgm?.loop !== false}
                  />
                )
              ) : (
                <Overlay
                  annotations={
                    track === "annotation" ? doc.tracks.annotation : undefined
                  }
                  clip={{
                    ...clip,
                    props: { ...clip.props, src: mediaUrl(clip.props?.src) },
                  }}
                  src={src}
                />
              )}
            </Sequence>
          );
        }),
      )}
    </AbsoluteFill>
  );
}
