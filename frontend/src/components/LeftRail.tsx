import { TranscriptPane } from "./TranscriptPane";
import { useRef } from "react";
import { Upload, Plus, Check, RotateCcw, Trash2, Film } from "lucide-react";
import { useStudio } from "@/store/studioStore";
import { assetClip, clipName, timecode } from "@/studio";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./ui/tabs";
import { Button } from "./ui/button";
export function LeftRail({ jump }: { jump: (ms: number) => void }) {
  const {
    timeline: doc,
    media,
    pins,
    select,
    selection,
    patchTimeline,
    upload,
    uploadProgress,
    editPin,
    deletePin,
  } = useStudio();
  const file = useRef<HTMLInputElement>(null);
  if (!doc) return null;
  async function files(list: FileList | null) {
    for (const item of Array.from(list ?? [])) await upload(item);
  }
  return (
    <Tabs className="rail" defaultValue="shots">
      <TabsList className="tab-list">
        {[
          ["shots", "镜头"],
          ["media", "素材"],
          ["transcript", "文稿"],
          ["pins", "图钉"],
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
      <TabsContent
        value="media"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          void files(e.dataTransfer.files);
        }}
      >
        <button
          className="upload-zone"
          disabled={uploadProgress !== null}
          onClick={() => file.current?.click()}
        >
          <Upload />
          {uploadProgress === null
            ? "拖入或选择素材"
            : uploadProgress === 100
              ? "正在处理代理…"
              : "上传 " + uploadProgress + "%"}
        </button>
        <input
          type="file"
          ref={file}
          multiple
          hidden
          accept=".mp4,.mov,.webm,.mp3,.m4a,.wav,.png,.jpg,.jpeg,.webp"
          onChange={(e) => {
            void files(e.target.files);
            e.target.value = "";
          }}
        />
        {media.map((a) => (
          <div className="rail-item media-item" key={a.id}>
            <Film />
            <span>
              <strong>{a.filename}</strong>
              <small>
                {a.proxy_path ? "720p 代理" : a.kind} ·{" "}
                {timecode(a.duration_ms ?? 0)}
              </small>
            </span>
            <Button
              variant="ghost"
              title={a.kind === "audio" ? "+ 插入音频轨" : "+ 插入主轨"}
              aria-label={a.kind === "audio" ? "+ 插入音频轨" : "+ 插入主轨"}
              onClick={() =>
                patchTimeline(
                  [{ op: "add_clip", ...assetClip(a, doc) }],
                  "插入素材",
                )
              }
            >
              <Plus />
              <span>{a.kind === "audio" ? "插入音频轨" : "插入主轨"}</span>
            </Button>
          </div>
        ))}
        {doc.tracks.video
          .filter((c) => c.source_state === "placeholder")
          .map((c) => (
            <div className="rail-item" key={c.id}>
              <Film />
              <span>
                <strong>{clipName(c)}</strong>
                <small>缺失占位</small>
              </span>
            </div>
          ))}
      </TabsContent>
      <TabsContent value="transcript">
        <TranscriptPane jump={jump} />
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
