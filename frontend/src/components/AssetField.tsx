import { useEffect, useState } from "react";
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
  useEffect(() => {
    request<Asset[]>("/" + pid + "/assets")
      .then(show)
      .catch((e) => fail(String(e)));
  }, [pid]);
  async function upload(file: File) {
    const data = new FormData();
    data.append("file", file);
    try {
      const r = await fetch("/api/projects/" + pid + "/assets", {
        method: "POST",
        body: data,
      });
      const a = await r.json();
      if (!r.ok) throw Error(a.detail);
      show((prev) => [...prev.filter((x) => x.asset_id !== a.asset_id), a]);
      onChange(a.asset_id);
      fail("");
    } catch (e) {
      fail(String(e));
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
      <label>
        导入图片
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
          }}
        />
      </label>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
