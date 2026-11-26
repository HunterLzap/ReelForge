import { useEffect, useState } from "react";
import { AudioLines, Scissors } from "lucide-react";
import { api, ApiError } from "@/api/client";
import { report, useStudio } from "@/store/studioStore";
import type { IssueKind, RoughCutPreview, TranscriptState } from "@/types";
import { timecode } from "@/studio";
import { Button } from "./ui/button";

const labels: Record<IssueKind, string> = {
  silence: "静音",
  filler: "口癖",
  retake: "重复句",
};
export function TranscriptPane({ jump }: { jump: (ms: number) => void }) {
  const timeline = useStudio((s) => s.timeline)!,
    accept = useStudio((s) => s.acceptTimeline);
  const [data, set] = useState<TranscriptState | null>(null),
    [preview, review] = useState<RoughCutPreview | null>(null),
    [filter, filters] = useState<IssueKind[]>(["silence", "filler", "retake"]),
    [busy, work] = useState(false),
    [multi, mode] = useState(false),
    [selected, select] = useState<string[]>([]),
    [buffer, padding] = useState(80);
  const { project_id: pid, revision } = timeline;
  useEffect(() => {
    let active = true;
    review(null);
    select([]);
    api
      .transcript(pid)
      .then((v) => {
        if (active) set(v);
      })
      .catch((e) => {
        if (active) {
          set(null);
          if (!(e instanceof ApiError && e.status === 404)) report(e);
        }
      });
    return () => {
      active = false;
    };
  }, [pid, revision]);
  async function run(fn: () => Promise<void>) {
    if (busy) return;
    work(true);
    try {
      await fn();
    } catch (e) {
      report(e);
    } finally {
      work(false);
    }
  }
  const issues = (data?.issues ?? []).filter((i) => filter.includes(i.kind));
  const highlighted = new Set(issues.flatMap((i) => i.word_ids));
  async function cut(apply: boolean, words = false) {
    const res = await api.roughCut(pid, {
      base_revision:
        preview && !words ? preview.base_revision : data!.base_revision,
      apply,
      buffer_ms: buffer,
      ...(words
        ? { delete_word_ids: selected }
        : { issue_ids: issues.map((i) => i.id) }),
    });
    if (res.timeline) {
      accept(res.timeline);
      select([]);
      review(null);
    } else review(res);
  }
  const stale = data?.base_revision !== revision;
  return (
    <div className="transcript-pane stack">
      <Button
        disabled={busy}
        onClick={() =>
          run(async () => {
            await api.transcribe(pid, revision);
            accept(await api.timeline(pid));
          })
        }
      >
        <AudioLines />
        {busy ? "处理中…" : "语音识别生成文稿"}
      </Button>
      {data && (
        <>
          <div className="row filter-chips">
            {(Object.keys(labels) as IssueKind[]).map((k) => (
              <button
                key={k}
                aria-pressed={filter.includes(k)}
                onClick={() => {
                  filters(
                    filter.includes(k)
                      ? filter.filter((v) => v !== k)
                      : [...filter, k],
                  );
                  review(null);
                }}
              >
                {labels[k]} {data.issues.filter((i) => i.kind === k).length}
              </button>
            ))}
          </div>
          <div className="between">
            <small>
              {data.transcript.engine} · {data.transcript.segments.length} 句
            </small>
            <label>
              <input
                type="checkbox"
                checked={multi}
                onChange={(e) => {
                  mode(e.target.checked);
                  select([]);
                }}
              />{" "}
              多选词句
            </label>
          </div>
          {data.transcript.segments.map((s) => (
            <div key={s.id} className="transcript-line">
              <time>{timecode(s.start_ms)}</time>
              <p>
                {s.words.map((w) => (
                  <button
                    key={w.id}
                    className={[
                      "word",
                      w.deleted ? "deleted" : "",
                      highlighted.has(w.id) ? "flagged" : "",
                      selected.includes(w.id) ? "selected" : "",
                    ].join(" ")}
                    aria-pressed={multi ? selected.includes(w.id) : undefined}
                    onClick={() => {
                      jump(w.start_ms);
                      if (multi && !w.deleted)
                        select(
                          selected.includes(w.id)
                            ? selected.filter((id) => id !== w.id)
                            : [...selected, w.id],
                        );
                    }}
                  >
                    {w.text}
                  </button>
                ))}
              </p>
            </div>
          ))}
          {multi && (
            <Button
              disabled={busy || stale || !selected.length}
              onClick={() => run(() => cut(true, true))}
            >
              删除选中词句并剪辑 ({selected.length})
            </Button>
          )}
          <details>
            <summary>呼吸留白 · {buffer} ms</summary>
            <input
              aria-label="呼吸留白"
              type="range"
              min={0}
              max={300}
              step={10}
              value={buffer}
              onChange={(e) => {
                padding(+e.target.value);
                review(null);
              }}
            />
          </details>
          <Button
            disabled={busy || stale || !issues.length}
            onClick={() => run(() => cut(false))}
          >
            <Scissors />
            三段式智能粗剪
          </Button>
          {preview && (
            <div className="cut-preview stack">
              {preview.issues.map((i) => (
                <button key={i.id} onClick={() => jump(i.start_ms)}>
                  {labels[i.kind]} · {i.text}
                </button>
              ))}
              <Button
                className="apply-cut"
                disabled={busy || !preview.saved_ms || stale}
                onClick={() => run(() => cut(true))}
              >
                一键应用粗剪 (省 {(preview.saved_ms / 1000).toFixed(1)}s)
              </Button>
            </div>
          )}
          <Button
            variant="ghost"
            disabled={busy || stale}
            onClick={() =>
              run(async () => accept(await api.syncSubtitles(pid, revision)))
            }
          >
            从文稿同步字幕
          </Button>
        </>
      )}
    </div>
  );
}
