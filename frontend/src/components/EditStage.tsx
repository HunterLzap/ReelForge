import { SubtitleTable } from "./SubtitleTable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { useEffect, useRef, useState } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import {
  Group,
  Panel,
  Separator,
  useDefaultLayout,
} from "react-resizable-panels";
import {
  Play,
  Pause,
  StepBack,
  StepForward,
  Scan,
  MonitorPlay,
} from "lucide-react";
import { useStudio } from "@/store/studioStore";
import { timecode, endOf } from "@/studio";
import type { TimelineDocument } from "@/types";
import { LeftRail } from "./LeftRail";
import { TimelinePanel } from "./TimelinePanel";
import { InspectorPanel } from "./InspectorPanel";
import { ReviewCanvas } from "./ReviewCanvas";
import { useComposition } from "./Composition";
import {
  useShortcut,
  usePlayback,
  seek,
  type PlayerHandle,
} from "./editorPlayback";
import { AspectControl } from "./StudioControls";
import { Button } from "./ui/button";
function Transport({
  doc,
  player,
  mode,
  toggle,
}: {
  doc: TimelineDocument;
  player: PlayerHandle;
  mode: boolean;
  toggle: () => void;
}) {
  const { frame, playing } = usePlayback();
  return (
    <div className="transport">
      <Button
        aria-label="上一帧"
        onClick={() => seek(player, ((frame - 1) * 1000) / doc.fps, doc.fps)}
      >
        <StepBack />
      </Button>
      <Button
        disabled={mode}
        aria-label={playing ? "暂停" : "播放"}
        onClick={() => player.current?.toggle()}
      >
        {playing ? <Pause /> : <Play />}
      </Button>
      <Button
        aria-label="下一帧"
        onClick={() => seek(player, ((frame + 1) * 1000) / doc.fps, doc.fps)}
      >
        <StepForward />
      </Button>
      <time>
        {timecode((frame * 1000) / doc.fps)}{" "}
        <span>/ {timecode(endOf(doc))}</span>
      </time>
      <AspectControl />
      <Button className={mode ? "on" : ""} aria-pressed={mode} onClick={toggle}>
        <Scan />
        画框批注 (M)
      </Button>
    </div>
  );
}
export function EditStage({ shortcuts }: { shortcuts: boolean }) {
  const doc = useStudio((s) => s.timeline)!;
  const player = useRef<PlayerRef>(null),
    source = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState(false);
  const props = useComposition(doc);
  const horizontal = useDefaultLayout({
      id: "rf-edit-columns",
      panelIds: ["rail", "preview", "inspector"],
    }),
    vertical = useDefaultLayout({
      id: "rf-edit-rows",
      panelIds: ["workbench", "timeline"],
    });
  useEffect(() => {
    const p = player.current;
    if (!p) return;
    const selection = useStudio.getState().selection;
    const clip =
      selection && "track" in selection
        ? doc.tracks[selection.track].find((c) => c.id === selection.id)
        : null;
    p.seekTo(clip ? Math.round((clip.start_ms * doc.fps) / 1000) : 0);
    usePlayback.setState({ frame: p.getCurrentFrame(), playing: false });
    const update = (e: { detail: { frame: number } }) =>
      usePlayback.setState({ frame: e.detail.frame });
    const play = () => usePlayback.setState({ playing: true }),
      pause = () => usePlayback.setState({ playing: false });
    p.addEventListener("frameupdate", update);
    p.addEventListener("play", play);
    p.addEventListener("pause", pause);
    p.addEventListener("ended", pause);
    return () => {
      p.removeEventListener("frameupdate", update);
      p.removeEventListener("play", play);
      p.removeEventListener("pause", pause);
      p.removeEventListener("ended", pause);
    };
  }, [doc.project_id]);
  function toggle() {
    player.current?.pause();
    setMode((v) => !v);
  }
  const jump = (ms: number) =>
    seek(
      player,
      Math.min(ms, ((props.durationInFrames - 1) * 1000) / doc.fps),
      doc.fps,
    );
  useShortcut("m", toggle, shortcuts);
  useShortcut("space", () => player.current?.toggle(), shortcuts && !mode);
  useShortcut(
    "left",
    () =>
      jump((((player.current?.getCurrentFrame() ?? 0) - 1) * 1000) / doc.fps),
    shortcuts && !mode,
  );
  useShortcut(
    "right",
    () =>
      jump((((player.current?.getCurrentFrame() ?? 0) + 1) * 1000) / doc.fps),
    shortcuts && !mode,
  );
  return (
    <Group
      className="edit-layout"
      orientation="vertical"
      defaultLayout={vertical.defaultLayout}
      onLayoutChanged={vertical.onLayoutChanged}
    >
      <Panel id="workbench" defaultSize="68%" minSize="35%">
        <Group
          orientation="horizontal"
          defaultLayout={horizontal.defaultLayout}
          onLayoutChanged={horizontal.onLayoutChanged}
        >
          <Panel id="rail" defaultSize="22%" minSize="14%">
            <LeftRail jump={jump} />
          </Panel>
          <Separator className="separator column" />
          <Panel id="preview" minSize="34%" defaultSize="54%">
            <div className="monitor">
              <div className="monitor-top">
                <span>
                  <MonitorPlay />
                  预览监视器
                </span>
                <time>
                  {doc.resolution.width} × {doc.resolution.height}
                </time>
              </div>
              <div className="viewport-fit">
                <div
                  className="viewport"
                  style={
                    {
                      "--ratio": doc.resolution.width / doc.resolution.height,
                    } as React.CSSProperties
                  }
                >
                  <div ref={source} className="player-source">
                    <Player
                      ref={player}
                      {...props}
                      style={{ width: "100%", height: "100%" }}
                      controls={false}
                    />
                  </div>
                  <ReviewCanvas
                    key={String(mode)}
                    mode={mode}
                    exit={() => setMode(false)}
                    source={source}
                    player={player}
                    jump={jump}
                  />
                </div>
              </div>
              <Transport
                doc={doc}
                player={player}
                mode={mode}
                toggle={toggle}
              />
            </div>
          </Panel>
          <Separator className="separator column" />
          <Panel id="inspector" defaultSize="24%" minSize="16%">
            <InspectorPanel />
          </Panel>
        </Group>
      </Panel>
      <Separator className="separator horizontal" />
      <Panel id="timeline" defaultSize="32%" minSize="18%">
        <Tabs className="edit-dock" defaultValue="timeline">
          <TabsList aria-label="剪辑面板" className="tab-list">
            <TabsTrigger value="timeline">时间轴</TabsTrigger>
            <TabsTrigger value="subtitles">极速字幕</TabsTrigger>
          </TabsList>
          <TabsContent value="timeline">
            <TimelinePanel jump={jump} shortcuts={shortcuts && !mode} />
          </TabsContent>
          <TabsContent value="subtitles">
            <SubtitleTable jump={jump} />
          </TabsContent>
        </Tabs>
      </Panel>
    </Group>
  );
}
