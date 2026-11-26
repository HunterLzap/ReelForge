/** @jsxRuntime classic */
import {
  React,
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  type ReactNode,
} from "../../../motion/src/skill-runtime";
import type { CardProps } from "../../../motion/src/types";

const gold = "#edc78e";
function Rise({
  delay = 0,
  children,
}: {
  delay?: number;
  children: ReactNode;
}) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({
    frame: f - delay,
    fps,
    config: { damping: 21, stiffness: 140 },
  });
  return (
    <div
      style={{ opacity: p, transform: "translateY(" + (1 - p) * 28 + "px)" }}
    >
      {children}
    </div>
  );
}
function Cover(p: CardProps) {
  return (
    <>
      {p.src && (
        <Img
          src={p.src}
          style={{ width: "100%", maxHeight: "32vh", objectFit: "cover" }}
        />
      )}
      <Rise>
        <h1 style={{ fontSize: "2.35em", lineHeight: 1.1, margin: "0.25em 0" }}>
          {p.title || p.heading}
        </h1>
      </Rise>
      <Rise delay={5}>{p.subtitle}</Rise>
    </>
  );
}
function Stat(p: CardProps) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const maximum = Math.max(1, ...(p.bars || []).map((b) => Math.abs(b.value)));
  return (
    <>
      <h2>{p.heading || p.label}</h2>
      {p.bars?.length ? (
        p.bars.map((b, i) => (
          <Rise key={i} delay={3 * i}>
            <div>
              {b.label}　
              <b>
                {b.value} {p.unit}
              </b>
            </div>
            <div
              style={{
                background: b.accent || gold,
                height: 12,
                margin: "0.2em 0 0.55em",
                width:
                  ((100 * Math.abs(b.value)) / maximum) *
                    spring({ frame: f - i * 3, fps }) +
                  "%",
              }}
            />
          </Rise>
        ))
      ) : (
        <Rise>
          <strong style={{ color: gold, fontSize: "3.6em" }}>
            {p.metric ?? p.value}
          </strong>{" "}
          {p.unit}
        </Rise>
      )}
      <Rise delay={6}>
        {p.takeaway || p.context}
        <small style={{ display: "block" }}>{p.delta}</small>
      </Rise>
    </>
  );
}
function Compare(p: CardProps) {
  const { width, height } = useVideoConfig();
  return (
    <>
      <h2>{p.heading || p.title}</h2>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: width >= height ? "1fr 1fr" : "1fr",
          gap: "1em",
        }}
      >
        {[
          [p.left_title, p.left_points],
          [p.right_title, p.right_points],
        ].map(([title, points], i) => (
          <Rise key={i} delay={4 * i}>
            <section style={{ borderTop: "4px solid " + gold, paddingTop: 16 }}>
              <b>{title}</b>
              {Array.isArray(points) &&
                points.map((v, j) => <p key={j}>{v}</p>)}
            </section>
          </Rise>
        ))}
      </div>
    </>
  );
}
function Steps(p: CardProps, timeline = false) {
  return (
    <>
      <h2>{p.heading || p.title}</h2>
      {(p.items || p.steps || []).map((item, i) => (
        <Rise key={i} delay={i * 3}>
          <div
            style={{
              display: "flex",
              gap: "0.65em",
              padding: ".32em 0",
              borderLeft: timeline ? "4px solid " + gold : undefined,
            }}
          >
            <b style={{ color: gold, minWidth: "1.6em", textAlign: "center" }}>
              {(typeof item === "object" && item.step_label) ||
                String(i + 1).padStart(2, "0")}
            </b>
            <span>
              {typeof item === "string" ? (
                item
              ) : (
                <>
                  <strong>{item.title || item.label}</strong>
                  <small style={{ display: "block", opacity: 0.78 }}>
                    {item.desc || item.detail}
                  </small>
                </>
              )}
            </span>
          </div>
        </Rise>
      ))}
    </>
  );
}
function Quote(p: CardProps) {
  return (
    <>
      <Rise>
        <blockquote
          style={{
            margin: 0,
            borderLeft: "8px solid " + gold,
            paddingLeft: ".55em",
            fontFamily: "Georgia,serif",
            fontSize: "1.95em",
          }}
        >
          {p.quote || p.text}
        </blockquote>
      </Rise>
      <Rise delay={7}>
        <p>{p.attribution}</p>
      </Rise>
    </>
  );
}
function Warning(p: CardProps) {
  return (
    <div
      style={{
        borderTop: "10px solid #efab74",
        background: "#3e2c26",
        padding: "1em",
      }}
    >
      <Rise>
        <h2>{p.heading || p.title}</h2>
      </Rise>
      <Rise delay={5}>{p.body || p.text}</Rise>
    </div>
  );
}
function Code(p: CardProps) {
  const f = useCurrentFrame();
  const code = p.code || "";
  return (
    <>
      <h2>{p.title || p.heading}</h2>
      <b style={{ color: gold }}>{p.language}</b>
      <pre
        style={{
          whiteSpace: "pre-wrap",
          background: "#101417",
          padding: ".8em",
          fontSize: ".82em",
          borderRadius: 16,
        }}
      >
        {code.slice(
          0,
          Math.ceil(
            interpolate(f, [0, 18], [0, code.length], {
              extrapolateRight: "clamp",
            }),
          ),
        )}
      </pre>
    </>
  );
}
function ImageCard(p: CardProps) {
  const { height } = useVideoConfig();
  return (
    <>
      <Rise>
        {p.src && (
          <Img
            src={p.src}
            style={{
              width: "100%",
              height: height * 0.43,
              objectFit: "cover",
              borderRadius: 16,
            }}
          />
        )}
      </Rise>
      <Rise delay={4}>
        <h2 style={{ margin: ".4em 0" }}>{p.heading || p.title}</h2>
        {p.caption}
      </Rise>
    </>
  );
}
const templates: Record<string, (props: CardProps) => ReactNode> = {
  cover: Cover,
  stat: Stat,
  compare: Compare,
  steps: Steps,
  quote: Quote,
  warning: Warning,
  code_card: Code,
  timeline_card: (p) => Steps(p, true),
  image_card: ImageCard,
};
export function EditorialCard({
  template,
  content,
  theme,
}: {
  template: string;
  content: CardProps;
  theme?: string;
}) {
  const { width, height } = useVideoConfig();
  const Card = templates[template] || Cover;
  const light = theme === "clean_light";
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        padding: Math.min(width, height) * 0.08,
        background: light
          ? "linear-gradient(125deg,#f6f1e8,#e9e6dc)"
          : "linear-gradient(125deg,#17242a,#172023 65%,#322b27)",
        color: light ? "#222d32" : "#f7f3ea",
        fontFamily: "Inter, PingFang SC, sans-serif",
        fontSize: Math.min(width, height) * 0.044,
        lineHeight: 1.28,
        overflow: "hidden",
        overflowWrap: "anywhere",
      }}
    >
      {content.tag && (
        <p
          style={{
            fontSize: ".65em",
            letterSpacing: ".12em",
            color: light ? "#70522a" : gold,
          }}
        >
          {content.tag}
        </p>
      )}
      <Card {...content} />
    </AbsoluteFill>
  );
}
