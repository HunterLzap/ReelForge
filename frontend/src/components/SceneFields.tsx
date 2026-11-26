export const names: Record<string, string> = {
  cover: "封面",
  image_card: "图片卡",
  big_quote: "金句",
  bullet_list: "编号卡片",
  stat_chart: "数据图表",
  compare_split: "对照",
  timeline: "时间线",
  hero_stat: "关键数字",
  checklist: "行动清单",
};
type Cell = string | number;
type Row = Record<string, Cell>;
export type Payload = Record<string, Cell | (string | Row)[]>;
const defaults: Record<string, Payload> = {
  image_card: {
    heading: "画面标题",
    caption: "配图说明",
    tag: "图记",
    layout: "split",
    image_asset: "",
  },
  cover: {
    cover_style: "grid",
    title: "专题封面",
    subtitle: "本期重点",
    tag: "专题",
  },
  big_quote: {
    quote: "先核实，再决定。",
    highlight: "先核实",
    attribution: "行动笔记",
  },
  bullet_list: {
    heading: "三个重点",
    items: ["准备", "核对", "记录"].map((label) => ({
      label,
      desc: "补充具体说明",
    })),
  },
  hero_stat: {
    metric: "100",
    unit: "元",
    label: "关键差额",
    context: "注明统计口径",
    delta: "与基准对比",
  },
  stat_chart: {
    heading: "数据对照",
    unit: "项",
    bars: ["甲", "乙", "丙"].map((label, i) => ({
      label,
      value: i + 1,
      accent: ["#689394", "#bd8845", "#957d96"][i],
    })),
    takeaway: "写下主要发现",
  },
  compare_split: {
    heading: "两种选择",
    left_title: "方案甲",
    left_points: ["第一项条件"],
    right_title: "方案乙",
    right_points: ["第二项条件"],
  },
  timeline: {
    heading: "行动路线",
    steps: ["准备", "执行", "复核"].map((title, i) => ({
      step_label: String(i + 1),
      title,
      desc: "具体动作",
    })),
  },
  checklist: {
    heading: "行动清单",
    items: [
      { status: "do", title: "核实", detail: "保存依据" },
      { status: "dont", title: "遗漏", detail: "逐项检查" },
    ],
  },
};
export function initial(kind: string, old: Payload = {}): Payload {
  const copy = structuredClone(defaults[kind]);
  for (const key of Object.keys(copy))
    if (typeof copy[key] === "string" && typeof old[key] === "string")
      copy[key] = old[key];
  return copy;
}
const labels: Record<string, string> = {
  heading: "标题",
  title: "标题",
  subtitle: "副标题",
  caption: "图片说明",
  tag: "栏目标签",
  quote: "引文",
  highlight: "高亮词",
  attribution: "署名",
  label: "标签",
  desc: "说明",
  items: "条目",
  unit: "单位",
  bars: "数据行",
  value: "数值",
  accent: "柱色",
  takeaway: "图表结论",
  left_title: "左栏标题",
  right_title: "右栏标题",
  left_points: "左栏要点",
  right_points: "右栏要点",
  steps: "步骤",
  step_label: "步骤标记",
  metric: "核心数字",
  context: "数字口径",
  delta: "变化说明",
  status: "行动类型",
  detail: "具体做法",
};
const fieldLimits: Record<string, number> = {
  title: 36,
  heading: 36,
  label: 24,
  left_title: 24,
  right_title: 24,
  attribution: 24,
  highlight: 24,
  tag: 16,
  step_label: 16,
  metric: 16,
  unit: 16,
};
function Field({ k, v, set }: { k: string; v: Cell; set: (v: Cell) => void }) {
  return (
    <label>
      {labels[k] || k}
      {k === "status" ? (
        <select
          aria-label={labels[k]}
          value={v}
          onChange={(e) => set(e.target.value)}
        >
          <option value="do">建议做</option>
          <option value="dont">避免做</option>
        </select>
      ) : (
        <input
          maxLength={fieldLimits[k] ?? 64}
          type={k === "accent" ? "color" : k === "value" ? "number" : "text"}
          value={v}
          onChange={(e) =>
            set(k === "value" ? Number(e.target.value) : e.target.value)
          }
        />
      )}
    </label>
  );
}
export function SceneFields({
  kind,
  data,
  set,
}: {
  kind: string;
  data: Payload;
  set: (p: Payload) => void;
}) {
  return (
    <>
      {Object.keys(defaults[kind]).map((k) => {
        const v = data[k];
        const change = (next: Payload[string]) => set({ ...data, [k]: next });
        if (k === "image_asset") return null;
        if (k === "layout" || k === "cover_style") {
          const options =
            k === "layout"
              ? { split: "图文分栏", framed: "装框", backdrop: "背景" }
              : { grid: "网格", arch: "拱形", wave: "波纹", minimal: "极简" };
          return (
            <label key={k}>
              {k === "layout" ? "配图布局" : "封面样式"}
              <select
                value={String(v || "grid")}
                onChange={(e) => change(e.target.value)}
              >
                {Object.entries(options).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        if (!Array.isArray(v))
          return <Field key={k} k={k} v={v} set={change} />;
        const min =
          k === "bars" || k === "steps" || kind === "bullet_list"
            ? 3
            : kind === "checklist"
              ? 2
              : 1;
        const max = k === "bars" ? 5 : 4;
        const replace = (i: number, val: string | Row) =>
          change(v.map((x, n) => (n === i ? val : x)));
        return (
          <fieldset key={k}>
            <legend>{labels[k]}</legend>
            {v.map((item, i) => (
              <div className="item-row" key={i}>
                <header>
                  <small>
                    {labels[k]} {i + 1}
                  </small>
                  <button
                    disabled={v.length <= min}
                    onClick={() => change(v.filter((_, n) => n !== i))}
                  >
                    移除
                  </button>
                </header>
                {typeof item === "string" ? (
                  <Field
                    k="detail"
                    v={item}
                    set={(s) => replace(i, String(s))}
                  />
                ) : (
                  Object.entries(item).map(([key, value]) => (
                    <Field
                      key={key}
                      k={key}
                      v={value}
                      set={(s) => replace(i, { ...item, [key]: s })}
                    />
                  ))
                )}
              </div>
            ))}
            <button
              disabled={v.length >= max}
              onClick={() =>
                change([
                  ...v,
                  structuredClone((defaults[kind][k] as (string | Row)[])[0]),
                ])
              }
            >
              添加{labels[k]}
            </button>
          </fieldset>
        );
      })}
    </>
  );
}
