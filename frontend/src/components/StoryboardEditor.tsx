import { useState, useEffect } from "react";
import { Detail, Act, Scene } from "../types";
import { request } from "../api/client";
import { Payload, SceneFields, names, initial } from "./SceneFields";
import AssetField from "./AssetField";
import PublishKit from "./PublishKit";
import OutlineApproval from "./OutlineApproval";
import PreviewStudio from "./PreviewStudio";

function visualKey(payload: Payload) {
  return JSON.stringify(payload, (_key, value) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.fromEntries(
        Object.entries(value)
          .filter(([, v]) => v != null)
          .sort(([a], [b]) => a.localeCompare(b)),
      );
    }
    return typeof value === "string" ? value.trim() : value;
  });
}

function useBlob(blob: Blob | null) {
  const [url, set] = useState("");
  useEffect(() => {
    const src = blob ? URL.createObjectURL(blob) : "";
    set(src);
    return () => {
      if (src) URL.revokeObjectURL(src);
    };
  }, [blob]);
  return url;
}

function Desk({
  p,
  s,
  act,
  choose,
  onDirty,
  view,
  mode,
  tab,
  selectTab,
}: {
  p: Detail;
  s: Scene;
  act: Act;
  choose: (id: string) => void;
  onDirty: (dirty: boolean) => void;
  view: string;
  mode: (s: string) => void;
  tab: string;
  selectTab: (s: string) => void;
}) {
  const [newKind, type] = useState<string | null>(null),
    [newData, set] = useState<Payload | null>(null),
    [newText, write] = useState<string | null>(null);
  const kind = newKind ?? s.template_type,
    data = newData ?? (s.visual_payload as Payload),
    narration = newText ?? s.narration;
  const [intent, ask] = useState("更口语化"),
    [image, picture] = useState<Blob | null>(null),
    [sound, listen] = useState<Blob | null>(null),
    [error, fail] = useState(""),
    [working, busy] = useState(false);
  const imageURL = useBlob(image),
    audioURL = useBlob(sound);
  const editable = ["COMPLETED", "WAITING_STORYBOARD"].includes(p.status);
  const base = "/" + p.id + "/scenes/" + s.id;
  const staticBase = "/workspace/" + p.id + "/scenes/" + s.id;
  const modified =
    kind !== s.template_type ||
    visualKey(data) !== visualKey(s.visual_payload as Payload) ||
    narration.trim() !== s.narration;
  const body = {
    template_type: kind,
    visual_payload: data,
    narration,
    source_ids: s.source_ids,
  };
  useEffect(() => {
    onDirty(modified);
    return () => onDirty(false);
  }, [modified, onDirty]);
  useEffect(() => {
    if (!modified) {
      set(null);
      type(null);
      write(null);
    }
  }, [modified]);
  async function save() {
    if (!editable || working || !modified) return;
    await action(async () => {
      await act("/scenes/" + s.id, "PATCH", body);
    });
  }
  useEffect(() => {
    function shortcut(e: KeyboardEvent) {
      if (
        !document.querySelector('[role="dialog"]') &&
        !e.isComposing &&
        (e.metaKey || e.ctrlKey) &&
        e.key.toLowerCase() === "s"
      ) {
        e.preventDefault();
        void save();
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  });
  useEffect(() => {
    if (!editable || !modified) {
      picture(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch("/api/projects" + base + "/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ template_type: kind, visual_payload: data }),
          signal: controller.signal,
        });
        if (!response.ok) throw Error("请填写完整的视觉字段以预览");
        const blob = await response.blob();
        if (!controller.signal.aborted) {
          picture(blob);
          fail("");
        }
      } catch (e) {
        if (!controller.signal.aborted) fail(String(e));
      }
    }, 450);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [base, kind, data, editable, s.content_hash, modified]);
  async function action(fn: () => Promise<void>) {
    busy(true);
    fail("");
    try {
      await fn();
    } catch (e) {
      fail(String(e));
    } finally {
      busy(false);
    }
  }
  async function audition() {
    const res = await fetch("/api/projects" + base + "/audition", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ narration }),
    });
    if (!res.ok) throw Error("试听生成失败");
    listen(await res.blob());
  }
  const ids = p.scenes.map((x) => x.id),
    idx = ids.indexOf(s.id);
  async function move(step: number) {
    const next = [...ids];
    [next[idx], next[idx + step]] = [next[idx + step], next[idx]];
    await act("/scenes/reorder", "PUT", { scene_ids: next });
  }
  const thumb = (row: Scene) =>
    row.content_hash && row.render_status === "READY"
      ? "/workspace/" +
        p.id +
        "/scenes/" +
        row.id +
        "/card.png?v=" +
        row.content_hash
      : "/api/projects/" +
        p.id +
        "/scenes/" +
        row.id +
        "/thumbnail?v=" +
        p.logs.at(-1)?.id;
  return (
    <div className="desk">
      <section className="canvas-area">
        <header>
          <h2>预览画布</h2>
          <div className="switch">
            <button aria-pressed={view === "card"} onClick={() => mode("card")}>
              单幕卡片
            </button>
            <button
              disabled={p.status !== "COMPLETED"}
              aria-pressed={view === "output"}
              onClick={() => mode("output")}
            >
              成片预览
            </button>
            {p.status === "COMPLETED" && (
              <button
                aria-pressed={view === "publish"}
                onClick={() => mode("publish")}
              >
                发布文案
              </button>
            )}
          </div>
        </header>
        {view === "publish" && p.status === "COMPLETED" ? (
          <PublishKit id={p.id} version={p.logs.at(-1)?.id ?? 0} />
        ) : view === "output" && p.status === "COMPLETED" ? (
          <PreviewStudio p={p} />
        ) : (
          <div className="canvas">
            {imageURL || s.content_hash || editable ? (
              <img
                alt={"第 " + s.order_index + " 幕预览"}
                src={imageURL || thumb(s)}
              />
            ) : (
              <span>等待渲染</span>
            )}
          </div>
        )}
        <div className="reel">
          <header>
            <h3>分镜轨</h3>
            <small>
              {idx + 1} / {ids.length}
            </small>
          </header>
          <div className="filmstrip">
            {p.scenes.map((x) => (
              <button
                className={x.id === s.id ? "chosen" : ""}
                key={x.id}
                onClick={() => {
                  if (
                    x.id !== s.id &&
                    (!modified || confirm("放弃当前草稿并切换分镜？"))
                  )
                    choose(x.id);
                }}
              >
                {(x.content_hash || editable) && <img alt="" src={thumb(x)} />}
                <span>
                  {x.order_index} · {names[x.template_type]}
                  <small>
                    {x.id === s.id && modified
                      ? "草稿"
                      : x.render_status === "READY"
                        ? "已渲染"
                        : "待渲染"}
                  </small>
                </span>
              </button>
            ))}
          </div>
          {editable && (
            <div className="tools">
              <button disabled={idx <= 1 || modified} onClick={() => move(-1)}>
                前移
              </button>
              <button
                disabled={idx === 0 || idx === ids.length - 1 || modified}
                onClick={() => move(1)}
              >
                后移
              </button>
              <button
                disabled={modified}
                onClick={() =>
                  act("/scenes", "POST", {
                    template_type: "checklist",
                    visual_payload: initial("checklist"),
                    source_ids: s.source_ids,
                    narration: "一起核对这份行动清单。",
                  })
                }
              >
                新增幕
              </button>
              <button
                disabled={idx === 0}
                onClick={() => {
                  if (confirm("删除当前分镜？"))
                    void act("/scenes/" + s.id, "DELETE");
                }}
              >
                删除幕
              </button>
            </div>
          )}
        </div>
      </section>
      <aside className="inspector">
        <header>
          <h2>分镜属性</h2>
          <small>
            {s.order_index} / {ids.length}
          </small>
        </header>
        <div className="switch tabs">
          {["画面内容", "旁白配音", "大纲核查"].map((x) => (
            <button
              key={x}
              aria-pressed={tab === x}
              onClick={() => selectTab(x)}
            >
              {x}
            </button>
          ))}
        </div>
        <div className="ins-scroll">
          {tab === "大纲核查" ? (
            <OutlineApproval {...{ p, act }} />
          ) : (
            <fieldset disabled={!editable || working}>
              {tab === "画面内容" ? (
                <>
                  <label>
                    模板
                    <select
                      aria-label="模板"
                      value={kind}
                      onChange={(e) => {
                        type(e.target.value);
                        set(initial(e.target.value, data));
                      }}
                    >
                      {Object.entries(names)
                        .filter(([k]) => (k === "cover") === (idx === 0))
                        .map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                    </select>
                  </label>
                  <SceneFields kind={kind} data={data} set={set} />
                  {["cover", "image_card"].includes(kind) && (
                    <AssetField
                      pid={p.id}
                      value={String(data.image_asset || "")}
                      onChange={(name) => {
                        const next = { ...data };
                        if (name) next.image_asset = name;
                        else delete next.image_asset;
                        set(next);
                      }}
                    />
                  )}
                </>
              ) : (
                <>
                  <label>
                    旁白
                    <textarea
                      aria-label="旁白"
                      rows={3}
                      maxLength={460}
                      value={narration}
                      onChange={(e) => {
                        write(e.target.value);
                        listen(null);
                      }}
                    />
                  </label>
                  <button onClick={() => action(audition)}>生成试听</button>
                  {(audioURL ||
                    (s.content_hash && p.target_format !== "cards_3_4")) && (
                    <audio
                      controls
                      src={
                        audioURL ||
                        staticBase + "/audio.mp3?v=" + s.content_hash
                      }
                    />
                  )}
                  {p.execution_mode !== "mcp" && (
                    <>
                      <label>
                        润色意图
                        <input
                          value={intent}
                          onChange={(e) => ask(e.target.value)}
                        />
                      </label>
                      <button
                        disabled={!intent.trim()}
                        onClick={() =>
                          action(async () => {
                            const r = await request<{ narration: string }>(
                              base + "/rewrite",
                              "POST",
                              { intent, narration },
                            );
                            write(r.narration);
                            listen(null);
                          })
                        }
                      >
                        AI 润色旁白
                      </button>
                    </>
                  )}
                  <small>{narration.length} / 460 字</small>
                </>
              )}
            </fieldset>
          )}
        </div>
        {error && <p role="alert">{error}</p>}
        <footer>
          <small>
            {modified
              ? "未保存草稿"
              : s.render_status === "READY"
                ? "已渲染"
                : "已保存（待渲染）"}
          </small>
          <button
            className="primary"
            disabled={!editable || working || !modified}
            onClick={save}
          >
            保存分镜
          </button>
        </footer>
      </aside>
    </div>
  );
}
export default function StoryboardEditor({
  p,
  act,
  onDirty,
}: {
  p: Detail;
  act: Act;
  onDirty: (x: boolean) => void;
}) {
  const [id, choose] = useState(""),
    [view, mode] = useState("card"),
    [tab, selectTab] = useState("画面内容");
  const s = p.scenes.find((x) => x.id === id) || p.scenes[0];
  return s ? (
    <Desk
      key={s.id}
      {...{ p, s, act, choose, onDirty, view, mode, tab, selectTab }}
    />
  ) : null;
}
