import { useEffect, useRef, useState } from "react";
import { Film, Plus, Upload } from "lucide-react";
import { toast } from "sonner";
import { api, resourceUrl } from "@/api/client";
import { useStudio, report } from "@/store/studioStore";
import { assetClip, timecode } from "@/studio";
import type { SourceHit, LibraryItem, MediaAsset } from "@/types";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./ui/tabs";

const flags: Record<string, string> = {
  low_res: "低分辨率",
  clipped_audio: "削波",
  aspect_mismatch: "比例不符",
  blurry: "模糊",
};
export function MaterialDrawer() {
  const {
    timeline: doc,
    media,
    upload,
    uploadProgress,
    patchTimeline,
    selection,
    receiveMedia,
  } = useStudio();
  const file = useRef<HTMLInputElement>(null);
  const [path, setPath] = useState(""),
    [keyword, setKeyword] = useState(""),
    [items, setItems] = useState<LibraryItem[]>([]);
  const [query, setQuery] = useState(""),
    [url, setUrl] = useState(""),
    [strategy, setStrategy] = useState("auto"),
    [kind, setKind] = useState("all"),
    [hits, setHits] = useState<SourceHit[]>([]),
    [busy, setBusy] = useState(""),
    [status, setStatus] = useState("");
  useEffect(() => {
    let active = true;
    api
      .librarySearch("")
      .then((r) => {
        if (active) setItems(r);
      })
      .catch(report);
    return () => {
      active = false;
    };
  }, []);
  if (!doc) return null;
  const pid = doc.project_id,
    aspect = doc.aspect_ratio;
  const selected =
    selection &&
    "track" in selection &&
    doc.tracks[selection.track].find(
      (c) => c.id === selection.id && c.kind === "placeholder",
    )
      ? selection
      : null;
  async function files(list: FileList | null) {
    for (const f of Array.from(list || [])) await upload(f);
  }
  async function run(label: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(label);
    setStatus("");
    try {
      await action();
    } catch (e) {
      report(e);
    } finally {
      setBusy("");
    }
  }
  async function insert(a: MediaAsset, replace: boolean) {
    const latest = useStudio.getState().timeline;
    if (latest?.project_id !== pid) return;
    receiveMedia(a);
    if (replace && selected) {
      const target = latest.tracks[selected.track].find(
        (c) => c.id === selected.id,
      );
      if (target?.kind !== "placeholder") {
        toast.info("所选占位已更新");
        return;
      }
      await patchTimeline(
        [
          {
            op: "update_clip",
            track: selected.track,
            clip_id: selected.id,
            patch: {
              kind: a.kind + "_clip",
              asset_id: a.id,
              source_state:
                a.source_type === "web_fetched"
                  ? "web_fetched"
                  : "local_matched",
              text: a.filename,
              component_id: "",
              src: "",
              prompt_hint: "",
              source_in_ms: 0,
              source_out_ms: null,
              speed:
                a.kind === "video" && a.duration_ms
                  ? Math.min(
                      1,
                      a.duration_ms / (target.end_ms - target.start_ms),
                    )
                  : 1,
            },
          },
        ],
        "替换选中占位",
      );
    } else {
      const entry = assetClip(a, latest);
      entry.clip.source_state =
        a.source_type === "web_fetched" ? "web_fetched" : "local_matched";
      await patchTimeline([{ op: "add_clip", ...entry }], "插入素材");
    }
  }
  async function collect(hit: {
    use_browser?: boolean;
    url: string;
    media_url?: string;
    license?: string;
  }) {
    const r = await api.sourceFetch(pid, hit);
    receiveMedia(r.asset);
    toast.success("已收入工程 · " + r.strategy);
    setStatus(r.asset.filename);
  }
  return (
    <Tabs defaultValue="project" className="materials">
      <TabsList className="tab-list">
        {[
          ["project", "工程素材"],
          ["library", "本地片库"],
          ["web", "联网采集"],
        ].map(([v, l]) => (
          <TabsTrigger key={v} value={v}>
            {l}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent
        value="project"
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
              {a.source_url && (
                <small>
                  <a target="_blank" rel="noreferrer" href={a.source_url}>
                    来源 URL
                  </a>{" "}
                  · {a.license}
                </small>
              )}
            </span>
            <Button
              variant="ghost"
              title={a.kind === "audio" ? "+ 插入音频轨" : "+ 插入主轨"}
              aria-label={a.kind === "audio" ? "+ 插入音频轨" : "+ 插入主轨"}
              onClick={() => insert(a, false)}
            >
              <Plus />
              <span>{a.kind === "audio" ? "插入音频轨" : "插入主轨"}</span>
            </Button>
          </div>
        ))}
      </TabsContent>
      <TabsContent value="library" className="stack">
        <Input
          aria-label="片库子目录"
          placeholder="片库子目录（默认 LIBRARY_ROOT）"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <Button
          disabled={!!busy}
          onClick={() =>
            run("扫描中", async () => {
              const r = await api.libraryIndex(path, aspect);
              setItems(r.items);
              setKeyword("");
              setStatus(
                "已索引 " +
                  r.items.length +
                  " 项" +
                  (r.errors.length
                    ? " · " +
                      r.errors.length +
                      " 项失败：" +
                      r.errors[0].message
                    : ""),
              );
            })
          }
        >
          扫描索引
        </Button>
        <form
          className="material-search"
          onSubmit={(e) => {
            e.preventDefault();
            void run("搜索中", async () => {
              const results = await api.librarySearch(keyword);
              setItems(results);
              setStatus("找到 " + results.length + " 项");
            });
          }}
        >
          <Input
            aria-label="片库关键词"
            placeholder="文件名、标签或画面关键词"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <Button type="submit" disabled={!!busy}>
            搜索
          </Button>
        </form>
        {items.map((a) => (
          <article className="material-entry" key={a.id}>
            {a.thumbnail_url && (
              <img loading="lazy" alt="" src={resourceUrl(a.thumbnail_url)} />
            )}
            <strong>{a.filename}</strong>
            <small>{a.caption}</small>
            <div className="quality-flags">
              {a.quality_flags.map((f) => (
                <span key={f}>{flags[f] || f}</span>
              ))}
            </div>
            <div className="topic-chips">
              <Button
                disabled={!!busy}
                onClick={() =>
                  run("导入中", async () =>
                    insert(await api.libraryImport(pid, a.id), false),
                  )
                }
              >
                + 插入
              </Button>
              {selected && a.kind !== "audio" && (
                <Button
                  disabled={!!busy}
                  onClick={() =>
                    run("替换中", async () =>
                      insert(await api.libraryImport(pid, a.id), true),
                    )
                  }
                >
                  替换选中占位
                </Button>
              )}
            </div>
          </article>
        ))}
      </TabsContent>
      <TabsContent value="web" className="stack">
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            void run("搜索中", async () => {
              const r = await api.sourceSearch(pid, query, kind);
              setHits(r.results);
              setStatus("找到 " + r.results.length + " 项");
            });
          }}
        >
          <Input
            placeholder="搜索公开文章、图片或视频"
            aria-label="联网关键词"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="material-search">
            <select
              aria-label="来源类型"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {[
                ["all", "全部"],
                ["article", "文章"],
                ["image", "开放图片"],
                ["video", "视频"],
              ].map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <Button type="submit" disabled={!!busy || !query.trim()}>
              联网搜索
            </Button>
          </div>
        </form>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            void run("提取中", () =>
              collect({
                url,
                use_browser:
                  strategy === "auto" ? undefined : strategy === "browser",
              }),
            );
          }}
        >
          <Input
            type="url"
            placeholder="或粘贴公开 URL"
            aria-label="公开 URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <select
            aria-label="网页提取方式"
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
          >
            <option value="auto">根据硬件自动选择</option>
            <option value="http">HTTP 正文提取</option>
            <option value="browser">浏览器抓取 · Crawl4AI / Playwright</option>
          </select>
          <Button type="submit" disabled={!!busy || !url.trim()}>
            提取网页 / 媒体
          </Button>
        </form>
        {hits.map((h) => (
          <article className="material-entry" key={h.url}>
            {h.thumbnail_url && <img alt="" src={h.thumbnail_url} />}
            <strong>{h.title}</strong>
            <a href={h.url} target="_blank" rel="noreferrer">
              来源 URL · {new URL(h.url).hostname}
            </a>
            <small>协议 · {h.license}</small>
            <Button
              disabled={!!busy}
              onClick={() => run("收入工程中", () => collect(h))}
            >
              + 收入工程
            </Button>
          </article>
        ))}
      </TabsContent>
      <small role="status">{busy || status}</small>
    </Tabs>
  );
}
