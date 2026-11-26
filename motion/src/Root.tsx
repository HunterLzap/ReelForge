import { Composition, registerRoot } from "remotion";
import { TimelinePlayer } from "./TimelinePlayer";
import type { TimelineDocument } from "./types";
import { durationMs, frames } from "./types";

const timeline: TimelineDocument = {
  version: "3.0",
  project_id: "preview",
  revision: 0,
  fps: 30,
  aspect_ratio: "16:9",
  resolution: { width: 1920, height: 1080 },
  tracks: { video: [], overlay: [], annotation: [], subtitle: [], audio: [] },
  bgm: null,
  subtitle_style: "pill_dark",
  export: {},
  meta: {},
};
export function Root() {
  return (
    <Composition
      id="Timeline"
      component={TimelinePlayer}
      defaultProps={{ timeline }}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={1}
      calculateMetadata={({ props }) => ({
        ...props.timeline.resolution,
        fps: props.timeline.fps,
        durationInFrames: Math.max(
          1,
          frames(durationMs(props.timeline), props.timeline.fps),
        ),
      })}
    />
  );
}
registerRoot(Root);
