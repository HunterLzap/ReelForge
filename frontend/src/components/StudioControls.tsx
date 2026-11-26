import { useState } from "react";
import { HardDrive, Command } from "lucide-react";
import { useStudio } from "@/store/studioStore";
import { Button } from "./ui/button";
import { Popover } from "./ui/popover";
import { Select } from "./ui/select";
import { aspects } from "@/studio";
import type { Aspect, PurgeScope } from "@/types";
export function AspectControl() {
  const doc = useStudio((s) => s.timeline)!;
  const patch = useStudio((s) => s.patchTimeline);
  return (
    <Select
      label="画幅"
      value={doc.aspect_ratio}
      options={doc.aspect_ratio === "3:4" ? [...aspects, "3:4"] : aspects}
      onChange={(aspect: Aspect) => {
        const resolutions = {
          "16:9": [1920, 1080],
          "9:16": [1080, 1920],
          "1:1": [1080, 1080],
          "3:4": [1080, 1440],
        };
        const [width, height] = resolutions[aspect];
        void patch(
          [
            {
              op: "set_export_spec",
              export: {
                ...doc.export,
                aspect_ratio: aspect,
                resolution: { width, height },
              },
            },
          ],
          "更改画幅",
        );
      }}
    />
  );
}
export function StorageCard() {
  const { storage, purge, project } = useStudio();
  const [scope, choose] = useState<PurgeScope>("temp"),
    [busy, setBusy] = useState(false);
  return (
    <div className="storage stack">
      <h3>{project ? "项目缓存" : "工作区存储"}</h3>
      <div className="muted">
        已用 {((storage?.used_bytes ?? 0) / 1048576).toFixed(1)} MB · 配额{" "}
        {((storage?.disk_limit_bytes ?? 0) / 1073741824).toFixed(0)} GB
      </div>
      <progress max={1} value={storage?.usage_ratio ?? 0} />
      <div className="row">
        <Select
          label="清理范围"
          value={scope}
          options={[
            { value: "temp", label: "临时文件" },
            { value: "proxies", label: "媒体代理" },
            { value: "all_cache", label: "临时文件和代理" },
          ]}
          onChange={choose}
        />
        <Button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            await purge(scope);
            setBusy(false);
          }}
        >
          清理
        </Button>
      </div>
    </div>
  );
}
export function StoragePill() {
  const storage = useStudio((s) => s.storage);
  return (
    <Popover
      trigger={
        <Button className="quota">
          <HardDrive />
          <span>
            存储{" "}
            {storage
              ? (storage.usage_ratio > 0 && storage.usage_ratio < 0.01
                  ? "<1"
                  : Math.round(storage.usage_ratio * 100)) + "%"
              : "…"}
          </span>
        </Button>
      }
    >
      <StorageCard />
    </Popover>
  );
}
export function CommandButton({ open }: { open: () => void }) {
  return (
    <Button aria-label="打开命令面板" onClick={open}>
      <Command size={14} /> K
    </Button>
  );
}
