// Skills live outside this package. Resolve React and Remotion through the player
// so CLI bundles and Vite consumers subscribe to the same frame context.
export { default as React } from "react";
export type { ReactNode } from "react";
export {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
