/** @jsxRuntime classic */
import {
  React,
  AbsoluteFill,
  Img,
  OffthreadVideo,
  spring,
  useVideoConfig,
  useCurrentFrame,
} from "../../../motion/src/skill-runtime";
import type { CardProps } from "../../../motion/src/types";

const templates = new Set([
  "news_headline",
  "lower_third",
  "ticker_banner",
  "chapter_card",
  "pip_commentary",
]);
export const isNewsTemplate = (id?: string) => templates.has(id || "");
const ink = "#102937",
  teal = "#89edcf",
  paper = "#f1f5ed";

export function NewsCard({
  template,
  content,
  video = false,
}: {
  template: string;
  content: CardProps;
  video?: boolean;
}) {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const unit = Math.min(width, height) / 100;
  const enter = spring({ frame, fps, config: { damping: 22 } });
  const title = content.title || content.heading || content.text || "";
  const slide = {
    transform: `translateY(${(1 - enter) * unit * 4}px)`,
    opacity: 0.35 + 0.65 * enter,
  };
  if (template === "lower_third")
    return (
      <div
        style={{
          position: "absolute",
          bottom: "22%",
          left: "6%",
          maxWidth: "85%",
          padding: "1.1% 2%",
          borderLeft: `${unit * 0.7}px solid ${teal}`,
          background: ink,
          color: "white",
          fontSize: unit * 4.2,
          fontWeight: 700,
          ...slide,
        }}
      >
        {content.tag && (
          <small style={{ display: "block", color: teal, fontSize: "0.62em" }}>
            {content.tag}
          </small>
        )}
        {title}
      </div>
    );
  if (template === "ticker_banner") {
    const line = content.text || title;
    return (
      <div
        style={{
          position: "absolute",
          bottom: 0,
          width: "100%",
          display: "flex",
          overflow: "hidden",
          background: ink,
          color: paper,
          fontSize: unit * 3.6,
          alignItems: "center",
        }}
      >
        <b
          style={{
            padding: ".22em .8em",
            background: teal,
            color: ink,
            zIndex: 1,
            whiteSpace: "nowrap",
          }}
        >
          快讯
        </b>
        <div
          style={{
            display: "flex",
            width: "max-content",
            transform: `translateX(calc(-${((frame / fps) * 6) % 100}% / 2))`,
            whiteSpace: "nowrap",
          }}
        >
          {[0, 1].map((i) => (
            <span key={i} style={{ minWidth: width, paddingInline: "1.2em" }}>
              {line}
            </span>
          ))}
        </div>
      </div>
    );
  }
  if (template === "pip_commentary") {
    const style = {
      width: "100%",
      aspectRatio: "16 / 9",
      objectFit: "cover" as const,
    };
    return (
      <div
        style={{
          position: "absolute",
          right: "5%",
          top: "7%",
          width: width > height ? "32%" : "52%",
          border: `${unit * 0.35}px solid ${teal}`,
          background: ink,
          color: "white",
          overflow: "hidden",
          ...slide,
        }}
      >
        {content.src &&
          (video ? (
            <OffthreadVideo src={content.src} muted style={style} />
          ) : (
            <Img src={content.src} style={style} />
          ))}
        <div style={{ padding: "6%", fontSize: unit * 3.4, fontWeight: 700 }}>
          {title}
          {content.body && (
            <div style={{ fontSize: ".75em", fontWeight: 400 }}>
              {content.body}
            </div>
          )}
        </div>
      </div>
    );
  }
  const chapter = template === "chapter_card";
  return (
    <AbsoluteFill
      style={{
        background: chapter ? paper : ink,
        color: chapter ? ink : paper,
        justifyContent: "center",
        padding: "8%",
        overflow: "hidden",
        fontFamily: "Inter, PingFang SC, sans-serif",
      }}
    >
      <div
        style={{
          borderTop: `${unit * 0.45}px solid ${chapter ? ink : teal}`,
          paddingTop: unit * 2,
          color: chapter ? ink : teal,
          fontWeight: 650,
          fontSize: unit * 2.8,
        }}
      >
        {content.tag || (chapter ? "章节导读" : "新闻速览")}
      </div>
      <div
        style={{
          fontSize: unit * (title.length > 28 ? 6.5 : 9),
          fontWeight: 800,
          lineHeight: 1.12,
          letterSpacing: "-.04em",
          marginBlock: unit * 4,
          overflowWrap: "anywhere",
          ...slide,
        }}
      >
        {title}
      </div>
      {content.subtitle && (
        <div style={{ maxWidth: "90%", fontSize: unit * 3.6, lineHeight: 1.5 }}>
          {content.subtitle}
        </div>
      )}
    </AbsoluteFill>
  );
}
