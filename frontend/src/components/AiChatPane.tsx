import { useState } from "react";
import { Undo2 } from "lucide-react";
import { useStudio } from "@/store/studioStore";
import { timecode, trackLabels } from "@/studio";
import { usePlayback } from "./editorPlayback";
import { Button } from "./ui/button";

const opNames: Record<string, string> = {
  add_clip: "添加片段",
  insert_clip: "插入片段",
  update_clip: "更新片段",
  delete_clip: "删除片段",
  split_clip: "分割片段",
  ripple_delete: "波纹删除",
  reorder: "重排片段",
  set_bgm: "更改配乐",
  set_export_spec: "更改导出设置",
  set_subtitle_style: "更改字幕样式",
  apply_plan: "应用分镜",
};

export function AiChatPane({ jump }: { jump: (ms: number) => void }) {
  const { timeline, pins, select, aiEdit, aiEdits, undoAi, busy } = useStudio();
  const [message, setMessage] = useState("");
  if (!timeline) return null;
  return (
    <section className="ai-pane stack">
      {pins
        .filter((p) => p.status === "open")
        .map((pin) => (
          <div className="ai-pin" key={pin.id}>
            <button
              className="ai-pin-note"
              onClick={() => {
                select({ pin: pin.id });
                jump(pin.time_ms);
              }}
            >
              <time>{timecode(pin.time_ms)}</time> {pin.note}
            </button>
            <Button disabled={busy} onClick={() => void aiEdit({ pin })}>
              交给 AI 修复
            </Button>
          </div>
        ))}
      <div role="log" aria-label="AI 改片记录" className="stack">
        {aiEdits.map((edit) => (
          <article key={edit.applied_revision} className="ai-diff">
            <p className="chat-turn user">{edit.message}</p>
            <strong>
              已应用 r{edit.previous_revision} → r{edit.applied_revision}
            </strong>
            <p>{edit.summary}</p>
            <div className="ai-badges">
              {edit.ops.map((op, i) => (
                <span key={i} title={op.clip_id}>
                  {op.track && op.track !== "all"
                    ? trackLabels[op.track] + " · "
                    : ""}
                  {opNames[op.op] ?? op.op}
                </span>
              ))}
            </div>
            <Button
              disabled={
                busy || edit.applied_revision !== timeline.history_revision
              }
              title={
                edit.applied_revision !== timeline.history_revision
                  ? "仅可撤销当前修订"
                  : undefined
              }
              onClick={() => void undoAi(edit.applied_revision)}
            >
              <Undo2 />
              撤销本次 AI 修改
            </Button>
          </article>
        ))}
      </div>
      <form
        className="stack"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!message.trim() || busy) return;
          const timeMs = Math.round(
            (usePlayback.getState().frame * 1000) / timeline.fps,
          );
          if (await aiEdit({ message: message.trim(), timeMs })) setMessage("");
        }}
      >
        <label className="field">
          对时间轴说话
          <textarea
            rows={3}
            maxLength={8000}
            value={message}
            disabled={busy}
            placeholder="例如：在 2 秒处加一个放大特写 / 把当前字幕改得更简洁"
            onChange={(e) => setMessage(e.target.value)}
          />
        </label>
        <Button type="submit" disabled={!message.trim() || busy}>
          {busy ? "正在处理…" : "应用修改"}
        </Button>
      </form>
    </section>
  );
}
