import { useState, useEffect, useRef } from "react";
import { Aperture, Plus, FolderOpen, Library } from "lucide-react";
import { Project, Detail, Act, formats, states } from "./types";
import { request } from "./api/client";
import CreateProjectModal from "./components/CreateProjectModal";
import PipelineGraph from "./components/PipelineGraph";
import OutlineApproval from "./components/OutlineApproval";
import StoryboardEditor from "./components/StoryboardEditor";

import SourceDrawer from "./components/SourceDrawer";
export default function App() {
  const [list, setList] = useState<Project[]>([]),
    [id, select] = useState(""),
    [p, show] = useState<Detail | null>(null),
    [modal, setModal] = useState(false),
    [drawer, setDrawer] = useState(false),
    [error, fail] = useState("");
  const selection = useRef(""),
    version = useRef(0);
  function choose(next: string) {
    if (next === selection.current) return;
    selection.current = next;
    select(next);
    show(null);
    setDrawer(false);
    fail("");
  }
  async function refresh(target: string) {
    const v = ++version.current;
    const data = await request<Detail>("/" + target);
    if (target === selection.current && v === version.current) {
      show(data);
      setList((prev) => prev.map((x) => (x.id === target ? data : x)));
    }
  }
  useEffect(() => {
    request<Project[]>("")
      .then((data) => {
        setList(data);
        if (data.length && !selection.current) {
          const wanted = new URLSearchParams(location.search).get("project");
          choose(data.find((x) => x.id === wanted)?.id || data[0].id);
        }
      })
      .catch((e) => fail(e.message));
  }, []);
  useEffect(() => {
    if (!id) return;
    let disposed = false;
    let events: EventSource | undefined;
    async function connect() {
      const d = await request<Detail>("/" + id);
      if (disposed) return;
      show(d);
      events = new EventSource(
        "/api/projects/" + id + "/stream?after=" + (d.logs.at(-1)?.id || 0),
      );
      events.onmessage = () => refresh(id).catch((e) => fail(e.message));
    }
    connect().catch((e) => fail(e.message));
    return () => {
      disposed = true;
      events?.close();
    };
  }, [id]);
  const act: Act = async (path, method = "POST", data) => {
    try {
      fail("");
      await request("/" + id + path, method, data);
      await refresh(id);
      return true;
    } catch (e) {
      fail(String(e));
      return false;
    }
  };
  async function create(data: unknown) {
    try {
      const proj = await request<Project>("", "POST", data);
      setList((prev) => [proj, ...prev]);
      setModal(false);
      choose(proj.id);
      await request("/" + proj.id + "/run", "POST");
      await refresh(proj.id);
    } catch (e) {
      fail(String(e));
    }
  }
  return (
    <>
      <nav>
        <div className="brand">
          <Aperture /> 映铸 <small>ReelForge</small>
        </div>
        <span>本地内容工作台</span>
      </nav>
      <div className="layout">
        <aside className="sidebar">
          <header>
            <h2>项目库</h2>
            <span>{list.length}</span>
          </header>
          <button className="primary" onClick={() => setModal(true)}>
            <Plus size={16} />
            新建项目
          </button>
          {p && <PipelineGraph p={p} />}
          {list.map((x) => (
            <button
              className={"project " + (x.id === id ? "selected" : "")}
              key={x.id}
              onClick={() => choose(x.id)}
            >
              <b>{x.topic}</b>
              <small>
                {formats[x.target_format]} · {states[x.status]}
              </small>
            </button>
          ))}
        </aside>
        <main>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {p ? (
            <>
              <header className="title">
                <div>
                  <small>
                    {formats[p.target_format]}　/　{states[p.status]}
                  </small>
                  <h1>{p.topic}</h1>
                </div>
                <button onClick={() => setDrawer(true)}>
                  <Library size={16} />
                  资料溯源
                </button>
              </header>
              {p.error_message && <p className="error">{p.error_message}</p>}
              {["PENDING", "FAILED"].includes(p.status) && (
                <button onClick={() => act("/run")}>
                  {p.status === "FAILED" ? "重试" : "启动"}
                </button>
              )}
              <StoryboardEditor {...{ p, act }} />
              <OutlineApproval {...{ p, act }} />
              <footer>
                文本用量 {p.total_tokens} tokens　·　预估 ¥
                {p.estimated_cost_cny.toFixed(4)}
              </footer>
            </>
          ) : !list.length ? (
            <div className="empty">
              <FolderOpen size={48} />
              <h1>创建第一个项目</h1>
              <p>输入选题，制作视频或图文卡片。</p>
              <button className="primary" onClick={() => setModal(true)}>
                新建项目
              </button>
            </div>
          ) : (
            <p>正在读取项目…</p>
          )}
        </main>
      </div>
      {modal && (
        <CreateProjectModal close={() => setModal(false)} create={create} />
      )}{" "}
      {drawer && p && <SourceDrawer p={p} close={() => setDrawer(false)} />}
    </>
  );
}
