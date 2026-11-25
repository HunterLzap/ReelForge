import { useState, FormEvent } from "react";
import { X } from "lucide-react";
import { formats } from "../types";
export default function CreateProjectModal({
  close,
  create,
}: {
  close: () => void;
  create: (data: unknown) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [theme, selectTheme] = useState("editorial_dark");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    try {
      await create({
        ...Object.fromEntries(f),
        auto_approve: f.has("auto_approve"),
      });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="overlay">
      <form role="dialog" aria-label="新建项目" onSubmit={submit}>
        <header>
          <h2>新建项目</h2>
          <button type="button" aria-label="关闭" onClick={close}>
            <X />
          </button>
        </header>
        <label>
          选题
          <input
            name="topic"
            required
            maxLength={240}
            autoFocus
            placeholder="例如：2026上海租房避坑"
          />
        </label>
        <label>
          导出规格
          <select name="target_format">
            {Object.entries(formats).map(([k, v]) => (
              <option value={k} key={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          视觉主题
          <select
            name="theme"
            value={theme}
            onChange={(e) => selectTheme(e.target.value)}
          >
            <option value="editorial_dark">黑金杂志</option>
            <option value="clean_light">瑞士暖白</option>
            <option value="warm_amber">复古暖棕</option>
          </select>
        </label>
        <div className={"theme-sample " + theme}>
          <i />
          <i />
          <i />
        </div>
        <label>
          频道署名
          <input name="brand_label" maxLength={32} placeholder="留空隐藏" />
        </label>
        <label>
          幕间转场
          <select name="transition">
            <option value="fade">叠化</option>
            <option value="slideleft">向左轻推</option>
          </select>
        </label>
        <label>
          配音
          <input name="voice" placeholder="使用默认中文女声" />
        </label>
        <label className="check">
          <input type="checkbox" name="auto_approve" />
          自动通过大纲与分镜审批
        </label>
        <button className="primary" disabled={busy}>
          创建并启动
        </button>
      </form>
    </div>
  );
}
