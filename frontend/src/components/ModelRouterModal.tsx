import { Fragment, useEffect, useState } from "react";
import { Copy, Cpu, Download, Settings2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useStudio, report } from "@/store/studioStore";
import type {
  CatalogEntry,
  DownloadTask,
  Hardware,
  ModelCenter,
  ModelConfig,
  Slot,
} from "@/types";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";
import { Field, Input } from "./ui/input";
import { Select } from "./ui/select";
import { Switch } from "./ui/switch";
import { Tabs, TabsList, TabsContent, TabsTrigger } from "./ui/tabs";

const labels: Record<Slot, string> = {
  llm_director: "编导",
  vlm_vision: "视觉",
  asr_speech: "语音识别",
  tts_voice: "语音合成",
  crawler_extract: "网页抽取",
};
const mirrors: Record<string, string> = {
  "hf-mirror": "HF-Mirror",
  modelscope: "ModelScope",
  ollama: "Ollama",
};

function SlotRow({
  slot,
  center,
  save,
}: {
  slot: Slot;
  center: ModelCenter;
  save: (config: ModelConfig) => void;
}) {
  const original = center.slots[slot];
  const [draft, set] = useState(original),
    [expanded, expand] = useState(false),
    [result, tested] = useState(""),
    [busy, working] = useState(false);
  const patch = (p: Partial<ModelConfig>) => {
    set({ ...draft, ...p });
    tested("");
  };
  const local = center.catalog.find((m) => m.id === draft.model);
  const blocked = !!(
    draft.enabled &&
    center.guarded &&
    (local?.size_mb ?? draft.model_size_mb) > 300
  );
  const dirty = JSON.stringify(draft) !== JSON.stringify(original);
  const presets = center.presets.filter(
    (p) =>
      slot !== "tts_voice" &&
      (slot !== "asr_speech" || ["openai", "dashscope"].includes(p.id)),
  );
  const engines = Array.from(
    new Set([
      draft.provider,
      ...presets.map((p) => p.id),
      ...(slot === "asr_speech"
        ? ["whisper_api", "sherpa_onnx", "faster_whisper"]
        : slot === "tts_voice"
          ? ["edge_tts"]
          : ["ollama"]),
    ]),
  );
  function provider(id: string) {
    const p = presets.find(
      (p) => p.id === id || (id === "whisper_api" && p.id === "openai"),
    );
    const entry = center.catalog.find(
      (m) => m.provider === id && m.slot === slot,
    );
    patch({
      provider: id,
      model:
        entry?.id ??
        (slot === "asr_speech"
          ? id === "dashscope"
            ? "paraformer-realtime-v2"
            : "whisper-1"
          : (p?.model ?? draft.model)),
      base_url:
        p?.base_url ?? (id === "ollama" ? "http://127.0.0.1:11434" : ""),
      api_key_env: p?.api_key_env ?? "",
      model_size_mb: entry?.size_mb ?? 0,
    });
  }
  async function action(test: boolean) {
    working(true);
    try {
      if (dirty) save(await api.saveModel(slot, draft));
      if (test) {
        const response = await api.testModel(slot);
        tested(response.message);
        (response.ok ? toast.success : toast.error)(response.message);
      } else toast.success("已保存槽位配置");
    } catch (e) {
      report(e);
    } finally {
      working(false);
    }
  }
  return (
    <Fragment>
      <tr>
        <th scope="row">
          <button
            className="slot-label"
            onClick={() => expand(!expanded)}
            aria-expanded={expanded}
          >
            {labels[slot]} <Settings2 size={14} />
          </button>
        </th>
        <td>
          <Select
            label={labels[slot] + "引擎"}
            value={draft.provider}
            options={engines.map((id) => ({
              value: id,
              label: center.presets.find((p) => p.id === id)?.name ?? id,
            }))}
            onChange={provider}
          />
        </td>
        <td>
          <Input
            aria-label={labels[slot] + "模型"}
            value={draft.model}
            onChange={(e) => patch({ model: e.target.value })}
          />
        </td>
        <td>
          <Switch
            label={labels[slot] + "启用"}
            checked={draft.enabled}
            onChange={(enabled) => patch({ enabled })}
          />
        </td>
        <td>
          <Button
            disabled={busy || blocked || !draft.enabled}
            onClick={() => action(true)}
          >
            测试
          </Button>
        </td>
      </tr>
      {(expanded || dirty || blocked || result) && (
        <tr>
          <td colSpan={5}>
            <div className="slot-detail">
              {center.catalog.some((m) => m.slot === slot) && (
                <Field label="本地模型目录">
                  <Select
                    label={labels[slot] + "本地目录"}
                    value={local?.id ?? "custom"}
                    options={[
                      { value: "custom", label: "自定义 / 云端" },
                      ...center.catalog
                        .filter((m) => m.slot === slot)
                        .map((m) => ({
                          value: m.id,
                          label:
                            m.id +
                            (center.guarded && m.size_mb > 300
                              ? " · 2C2G 已锁定"
                              : ""),
                          disabled: center.guarded && m.size_mb > 300,
                        })),
                    ]}
                    onChange={(id) => {
                      const m = center.catalog.find((m) => m.id === id);
                      if (m)
                        patch({
                          provider: m.provider,
                          model: id,
                          model_size_mb: m.size_mb,
                          api_key_env: "",
                          base_url:
                            m.provider === "ollama"
                              ? "http://127.0.0.1:11434"
                              : "",
                        });
                      else patch({ model: "", model_size_mb: 0 });
                    }}
                  />
                </Field>
              )}
              <Field label="Base URL">
                <Input
                  value={draft.base_url}
                  onChange={(e) => patch({ base_url: e.target.value })}
                />
              </Field>
              <Field label="API Key 环境变量">
                <Input
                  value={draft.api_key_env}
                  onChange={(e) => patch({ api_key_env: e.target.value })}
                />
              </Field>
              <Button
                disabled={!dirty || busy || blocked}
                onClick={() => action(false)}
              >
                保存
              </Button>
              {(blocked || result) && (
                <small>{blocked ? center.guard_explanation : result}</small>
              )}
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

function CatalogRow({
  entry,
  guarded,
  task,
  refresh,
}: {
  entry: CatalogEntry;
  guarded: boolean;
  task?: DownloadTask;
  refresh: () => Promise<void>;
}) {
  const [mirror, set] = useState(entry.mirrors[0]);
  const blocked = guarded && entry.size_mb > 300,
    running = task?.status === "downloading";
  async function change() {
    try {
      if (running) await api.cancelDownload(task!.task_id);
      else await api.download(entry.id, mirror);
      await refresh();
    } catch (e) {
      report(e);
    }
  }
  return (
    <div className="catalog-row">
      <div>
        <strong>{entry.id}</strong>
        <small>
          {entry.size_mb} MB{blocked ? " · 2C2G 已锁定" : ""}
        </small>
      </div>
      <Select
        label={entry.id + "镜像"}
        value={mirror}
        options={entry.mirrors.map((v) => ({ value: v, label: mirrors[v] }))}
        onChange={set}
      />
      <Button disabled={blocked && !running} onClick={change}>
        {running ? "取消" : task?.status === "cancelled" ? "继续" : "下载"}
      </Button>
      {task && (
        <div className="download-progress">
          <progress value={task.percentage} max={100} />
          <small>
            {task.mock ? "模拟 · " : ""}
            {task.percentage}% · {(task.downloaded_bytes / 1e6).toFixed(2)} MB ·{" "}
            {task.error ??
              {
                completed: "已完成",
                cancelled: "已取消",
                downloading: "下载中",
                failed: "失败",
              }[task.status]}
          </small>
        </div>
      )}
    </div>
  );
}

export function ModelRouterModal() {
  const { modelCenter, showModels } = useStudio();
  const [center, set] = useState<ModelCenter | null>(null),
    [hardware, hw] = useState<Hardware | null>(null),
    [probing, probeBusy] = useState(false),
    [tasks, downloads] = useState<DownloadTask[]>([]),
    [snippet, mcp] = useState("");
  async function probe() {
    probeBusy(true);
    try {
      hw(await api.probe());
    } catch (e) {
      report(e);
    } finally {
      probeBusy(false);
    }
  }
  const refresh = async () => downloads(await api.downloads());
  useEffect(() => {
    api.models().then(set).catch(report);
    refresh().catch(report);
    api
      .engines()
      .then((r) => mcp(JSON.stringify(r.mcp_config, null, 2)))
      .catch(report);
    if (modelCenter === "probe") void probe();
  }, [modelCenter]);
  useEffect(() => {
    const stream = api.downloadEvents();
    stream.onmessage = (e) => downloads(JSON.parse(e.data));
    return () => stream.close();
  }, []);
  const policy = hardware ?? center;
  return (
    <Dialog
      open
      onOpenChange={(v) => {
        if (!v) showModels(null);
      }}
      title="模型中心"
    >
      <div className="model-center stack">
        <section className="hardware">
          <div className="between">
            <h3>
              <Cpu size={17} /> 本机硬件
            </h3>
            <Button disabled={probing} onClick={probe}>
              {probing ? "探测中…" : "探测硬件"}
            </Button>
          </div>
          {policy && (
            <p>
              当前 {policy.active_profile} · 推荐 {policy.recommended_profile}
            </p>
          )}
          {hardware && (
            <div className="row hardware-pills">
              {[
                `CPU ${hardware.cpu_cores} 核`,
                `RAM ${hardware.ram_available_gb.toFixed(1)} / ${hardware.ram_total_gb.toFixed(1)} GB`,
                `磁盘可用 ${hardware.disk_free_gb.toFixed(1)} GB`,
                hardware.gpu.cuda
                  ? "CUDA"
                  : hardware.gpu.mps
                    ? "Metal / MPS"
                    : "CPU 推理",
                ...Object.entries({
                  ...hardware.binaries,
                  ...Object.fromEntries(
                    Object.entries(hardware.services).map(([k, v]) => [
                      k + " 服务",
                      v,
                    ]),
                  ),
                }).map(([name, ok]) => name + " " + (ok ? "✓" : "—")),
              ].map((v) => (
                <span key={v}>{v}</span>
              ))}
            </div>
          )}
          {policy?.guarded && <small>{policy.guard_explanation}</small>}
        </section>
        <Tabs defaultValue="slots">
          <TabsList className="tab-list">
            {[
              ["slots", "模型路由"],
              ["catalog", "本地下载"],
              ["mcp", "MCP 配置"],
            ].map(([id, title]) => (
              <TabsTrigger key={id} value={id}>
                {title}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="slots">
            {center && (
              <table className="routing-table">
                <thead>
                  <tr>
                    {["任务槽位", "引擎", "模型", "状态", "测试"].map((v) => (
                      <th key={v}>{v}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(Object.keys(labels) as Slot[]).map((slot) => (
                    <SlotRow
                      key={slot}
                      slot={slot}
                      center={center}
                      save={(config) =>
                        set(
                          (current) =>
                            current && {
                              ...current,
                              slots: { ...current.slots, [slot]: config },
                            },
                        )
                      }
                    />
                  ))}
                </tbody>
              </table>
            )}
          </TabsContent>
          <TabsContent value="catalog">
            <h3 className="catalog-heading">
              <Download size={16} /> 镜像下载
            </h3>
            {center?.catalog.map((entry) => (
              <CatalogRow
                key={entry.id}
                entry={entry}
                guarded={policy!.guarded}
                task={tasks.find((t) => t.model === entry.id)}
                refresh={refresh}
              />
            ))}
          </TabsContent>
          <TabsContent value="mcp">
            <pre>{snippet}</pre>
            <Button
              onClick={() =>
                navigator.clipboard
                  .writeText(snippet)
                  .then(() => toast.success("已复制 stdio 配置"))
                  .catch(report)
              }
            >
              <Copy />
              复制 MCP 配置
            </Button>
          </TabsContent>
        </Tabs>
      </div>
    </Dialog>
  );
}
