import { useEffect, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { request } from "../api/client";
interface Asset {
  asset_id: string;
  url: string;
}
export default function AssetField({
  pid,
  value,
  onChange,
}: {
  pid: string;
  value: string;
  onChange: (name: string) => void;
}) {
  const [list, show] = useState<Asset[]>([]),
    [error, fail] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const projectScope = useRef<AbortController | null>(null);
  const selectAsset = useRef(onChange);
  const [uploading, setUploading] = useState(false);
  const [fileName, setFileName] = useState("");
  useEffect(() => {
    selectAsset.current = onChange;
  }, [onChange]);
  useEffect(() => {
    const scope = new AbortController();
    projectScope.current = scope;
    show([]);
    fail("");
    setFileName("");
    setUploading(false);
    request<Asset[]>("/" + pid + "/assets")
      .then((assets) => {
        if (!scope.signal.aborted) {
          show((current) => [
            ...assets.filter((a) => !current.some((x) => x.asset_id === a.asset_id)),
            ...current,
          ]);
        }
      })
      .catch((e) => {
        if (!scope.signal.aborted) fail(String(e));
      });
    return () => scope.abort();
  }, [pid]);
  async function upload(file: File) {
    const signal = projectScope.current?.signal;
    setFileName(file.name);
    setUploading(true);
    fail("");
    const data = new FormData();
    data.append("file", file);
    try {
      const r = await fetch("/api/projects/" + pid + "/assets", {
        method: "POST",
        body: data,
        signal,
      });
      const a = await r.json();
      if (signal?.aborted) return;
      if (!r.ok) throw Error(a.detail);
      show((prev) => [...prev.filter((x) => x.asset_id !== a.asset_id), a]);
      selectAsset.current(a.asset_id);
    } catch (e) {
      if (!signal?.aborted) fail(String(e));
    } finally {
      if (!signal?.aborted) setUploading(false);
    }
  }
  return (
    <div>
      <label>
        图片素材
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">选择本地图片</option>
          {list.map((a) => (
            <option key={a.asset_id} value={a.asset_id}>
              {a.asset_id.slice(0, 10)} · {a.asset_id.split(".").pop()}
            </option>
          ))}
        </select>
      </label>
      <div className="upload-field">
        <span className="field-label">导入图片</span>
        <div className="upload-box">
          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            aria-label="导入图片"
            tabIndex={-1}
            disabled={uploading}
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void upload(file);
            }}
          />
          <button
            type="button"
            className="upload-btn"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            <Upload size={14} aria-hidden="true" />
            {uploading ? "上传中…" : "选择图片"}
          </button>
          <span
            className={fileName ? "upload-name has-file" : "upload-name"}
            title={uploading ? `正在上传 ${fileName}` : fileName || "未选择文件"}
            role="status"
          >
            {uploading ? `正在上传 ${fileName}…` : fileName || "未选择文件"}
          </span>
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
