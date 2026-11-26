import { AiChatPane } from "./AiChatPane";
import { TranscriptPane } from "./TranscriptPane";
import { MaterialDrawer } from "./MaterialDrawer";
import { Check, RotateCcw, Trash2 } from "lucide-react";
import { useStudio } from "@/store/studioStore";
import { clipName, timecode } from "@/studio";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./ui/tabs";
import { Button } from "./ui/button";
export function LeftRail({ jump }: { jump: (ms: number) => void }) {
  const {
    timeline: doc,
    railTab,
    setRailTab,
    pins,
    select,
    selection,
    editPin,
    deletePin,
  } = useStudio();
  if (!doc) return null;
  return (
    <Tabs className="rail" value={railTab} onValueChange={setRailTab}>
      <TabsList className="tab-list">
        {[
          ["shots", "镜头"],
          ["media", "素材"],
          ["transcript", "文稿"],
          ["pins", "图钉"],
          ["ai", "AI 改片"],
        ].map(([id, label]) => (
          <TabsTrigger value={id} key={id}>
            {label}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="shots">
        {doc.tracks.video.length === 0 && (
          <p className="empty">时间轴上还没有镜头</p>
        )}
        {doc.tracks.video.map((c, i) => (
          <button
            className={
              "rail-item " +
              (selection && "id" in selection && selection.id === c.id
                ? "selected"
                : "")
            }
            key={c.id}
            onClick={() => {
              select({ track: "video", id: c.id });
              jump(c.start_ms);
            }}
          >
            <b className="rail-index">{String(i + 1).padStart(2, "0")}</b>
            <span>
              <strong>{clipName(c)}</strong>
              <small>
                {timecode(c.start_ms)} ·{" "}
                {c.source_state === "placeholder"
                  ? "缺失占位"
                  : timecode(c.end_ms - c.start_ms)}
              </small>
            </span>
          </button>
        ))}
      </TabsContent>
      <TabsContent value="media">
        <MaterialDrawer />
      </TabsContent>
      <TabsContent value="transcript">
        <TranscriptPane jump={jump} />
      </TabsContent>
      <TabsContent value="ai">
        <AiChatPane jump={jump} />
      </TabsContent>
      <TabsContent value="pins">
        {!pins.length && <p className="empty">按 M 在画面上框选并添加批注。</p>}
        {pins.map((p, i) => (
          <div key={p.id} className="pin-row">
            <button
              className="rail-item"
              onClick={() => {
                select({ pin: p.id });
                jump(p.time_ms);
              }}
            >
              <b>{i + 1}</b>
              <span>
                <strong>{p.note}</strong>
                <small>
                  {timecode(p.time_ms)} ·{" "}
                  {p.status === "open" ? "待处理" : "已解决"}
                </small>
              </span>
            </button>
            <Button
              variant="ghost"
              aria-label={p.status === "open" ? "解决批注" : "重新打开"}
              onClick={() =>
                editPin(p.id, {
                  status: p.status === "open" ? "resolved" : "open",
                  resolved_by_revision: doc.revision,
                })
              }
            >
              {p.status === "open" ? <Check /> : <RotateCcw />}
            </Button>
            <Button
              variant="ghost"
              aria-label="删除批注"
              onClick={() => deletePin(p.id)}
            >
              <Trash2 />
            </Button>
          </div>
        ))}
      </TabsContent>
    </Tabs>
  );
}
