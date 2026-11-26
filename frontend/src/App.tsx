import { useState, useEffect, useRef } from "react";
import {
  Aperture,
  Plus,
  FolderOpen,
  Library,
  Copy,
  Plug,
  Square,
  Play,
  Search,
  Clapperboard,
} from "lucide-react";
import { Project, Detail, Act, formats, states } from "./types";
import { request } from "./api/client";
import CreateProjectModal from "./components/CreateProjectModal";
import PipelineGraph, { Trace } from "./components/PipelineGraph";
import OutlineApproval from "./components/OutlineApproval";
import StoryboardEditor from "./components/StoryboardEditor";

import SourceDrawer from "./components/SourceDrawer";
import {
  EngineConnection,
  Engines,
  labels,
} from "./components/EngineConnection";
export default function App() {
  const [engines, setEngines] = useState<Engines | null>(null);
  const [connectModal, setConnectModal] = useState(false);
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
    history.replaceState(
      null,
      "",
      next ? "?project=" + next : location.pathname,
    );
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
    fetch("/api/system/engines")
      .then((r) => {
        if (!r.ok) throw Error("无法读取执行引擎");
        return r.json();
      })
      .then(setEngines)
      .catch((e) => fail(String(e)));
    let disposed = false;
    const loadProjects = () =>
      request<Project[]>("")
        .then((data) => {
          if (disposed) return;
          setList(data);
          if (data.length && !selection.current) {
            const wanted = new URLSearchParams(location.search).get("project");
            choose(data.find((x) => x.id === wanted)?.id || data[0].id);
          }
        })
        .catch((e) => {
          if (!disposed) fail(e.message);
        });
    void loadProjects();
    const timer = window.setInterval(loadProjects, 5000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
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
      if (proj.execution_mode === "mcp") setConnectModal(true);
      else await request("/" + proj.id + "/run", "POST");
      await refresh(proj.id);
    } catch (e) {
      fail(String(e));
    }
  }
  const [q, search] = useState(""),
    [filter, filterBy] = useState(""),
    [trace, showTrace] = useState(false),
    [mobileLibrary, toggleLibrary] = useState(false);
  const [cloneTarget, setClone] = useState<Project | null>(null),
    [dirty, setDirty] = useState(false);
  const active =
    !!p &&
    [
      "RESEARCHING",
      "FACT_CHECKING",
      "DIRECTING",
      "RENDERING",
      "ASSEMBLING",
    ].includes(p.status);
  function selectProject(next: string) {
    if (next === id || !dirty || confirm("放弃当前分镜草稿？")) {
      choose(next);
      toggleLibrary(false);
    }
  }
  async function remove(x: Project) {
    if (!confirm("删除项目「" + x.topic + "」及其所有产物？")) return;
    try {
      await request("/" + x.id, "DELETE");
      const rest = list.filter((r) => r.id !== x.id);
      setList(rest);
      if (x.id === id) choose(rest[0]?.id || "");
    } catch (e) {
      fail(String(e));
    }
  }
  async function clone(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!cloneTarget) return;
    try {
      const proj = await request<Project>(
        "/" + cloneTarget.id + "/clone",
        "POST",
        Object.fromEntries(new FormData(e.currentTarget)),
      );
      setList((prev) => [proj, ...prev]);
      setClone(null);
      choose(proj.id);
      toggleLibrary(false);
    } catch (e) {
      fail(String(e));
    }
  }
  const primary = !p
    ? null
    : active
      ? ["停止", "/cancel"]
      : p.status === "WAITING_STORYBOARD"
        ? ["确认并渲染", "/approve"]
        : p.status === "COMPLETED"
          ? ["重渲染", "/rebuild"]
          : p.status === "WAITING_OUTLINE" &&
              p.fact_check &&
              p.execution_mode !== "mcp"
            ? ["通过大纲", "/approve"]
            : ["CANCELLED", "FAILED"].includes(p.status) && p.scenes.length
              ? ["重新渲染", "/render"]
              : ["PENDING", "FAILED", "CANCELLED"].includes(p.status) &&
                  p.execution_mode !== "mcp"
                ? ["启动", "/run"]
                : null;
  return (
    <div
      className="studio h-screen overflow-hidden"
      onKeyDownCapture={(e) => {
        if (e.nativeEvent.isComposing && e.key === "Enter") e.preventDefault();
        if (e.key === "Escape" && !e.nativeEvent.isComposing) {
          setModal(false);
          setDrawer(false);
          setConnectModal(false);
          showTrace(false);
          setClone(null);
          toggleLibrary(false);
        }
      }}
    >
      <nav className="topbar">
        <div className="brand">
          <Aperture size={22} />
          <strong>ReelForge</strong>
        </div>
        <button
          className="library-toggle"
          aria-label="切换项目库"
          onClick={() => toggleLibrary(!mobileLibrary)}
        >
          <FolderOpen size={16} />
        </button>
        {p && (
          <>
            <h1 title={p.topic}>{p.topic}</h1>
            <span className="chip">{labels[p.execution_mode]}</span>
            <span className="chip format-chip">
              {formats[p.target_format].split(" ")[0]}
            </span>
            <span className="chip status-chip">
              {active
                ? "运行中"
                : p.status === "COMPLETED" &&
                    p.scenes.some((s) => s.render_status === "DIRTY")
                  ? "待渲染"
                  : states[p.status]}
            </span>
            <PipelineGraph p={p} open={() => showTrace(true)} />
            <div className="top-actions">
              <button
                title="转画幅克隆"
                aria-label="转画幅克隆"
                disabled={!p.scenes.length || active}
                onClick={() => setClone(p)}
              >
                <Copy />
                <span>转画幅</span>
              </button>
              <button
                title="MCP 接入"
                aria-label="MCP 接入"
                onClick={() => setConnectModal(true)}
              >
                <Plug />
                <span>MCP 接入</span>
              </button>
              <button
                title="资料溯源"
                aria-label="资料溯源"
                onClick={() => setDrawer(true)}
              >
                <Library />
                <span>资料溯源</span>
              </button>
              {primary && (
                <button
                  className="primary"
                  disabled={dirty && !active}
                  onClick={() =>
                    act(
                      primary[1],
                      "POST",
                      primary[1] === "/render" ? { wait: false } : undefined,
                    )
                  }
                >
                  {active ? <Square /> : <Play />}
                  {primary[0]}
                </button>
              )}
            </div>
          </>
        )}
      </nav>
      <div className="body-grid">
        <aside className={"library " + (mobileLibrary ? "opened" : "")}>
          <header>
            <h2>项目库</h2>
            <small>{list.length}</small>
          </header>
          <button className="primary w-full" onClick={() => setModal(true)}>
            <Plus size={15} />
            新建项目
          </button>
          <label className="search">
            <Search size={15} />
            <input
              aria-label="搜索项目"
              placeholder="搜索项目"
              value={q}
              onChange={(e) => search(e.target.value)}
            />
          </label>
          <select
            aria-label="画幅筛选"
            value={filter}
            onChange={(e) => filterBy(e.target.value)}
          >
            <option value="">全部画幅</option>
            {Object.entries(formats).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <div className="projects">
            {list
              .filter(
                (x) =>
                  x.topic.toLowerCase().includes(q.toLowerCase()) &&
                  (!filter || x.target_format === filter),
              )
              .map((x) => (
                <div
                  key={x.id}
                  className={"project-row " + (x.id === id ? "selected" : "")}
                >
                  <button
                    className="project"
                    onClick={() => selectProject(x.id)}
                  >
                    <b>{x.topic}</b>
                    <small>
                      {formats[x.target_format].split(" ")[0]} ·{" "}
                      {states[x.status]}
                    </small>
                  </button>
                  <details className="row-menu">
                    <summary aria-label="项目操作">•••</summary>
                    <div>
                      <button onClick={() => setClone(x)}>克隆转画幅</button>
                      <button onClick={() => remove(x)}>删除项目</button>
                    </div>
                  </details>
                </div>
              ))}
          </div>
          <footer>
            <span>项目用量</span>
            <strong>
              {p &&
              (p.total_tokens > 0 ||
                (engines?.mock_llm &&
                  p.stage_runs.some((r) =>
                    [
                      "Researcher",
                      "FactChecker",
                      "Director",
                      "SceneWriter",
                    ].includes(r.stage_name),
                  )))
                ? p.total_tokens
                : "—"}{" "}
              <small>tokens</small>
            </strong>
          </footer>
        </aside>
        <main>
          {p?.error_message && <p role="alert">{p.error_message}</p>}
          {p?.scenes.length ? (
            <StoryboardEditor key={p.id} {...{ p, act }} onDirty={setDirty} />
          ) : (
            <div className="empty">
              {p?.research ? (
                <OutlineApproval {...{ p, act }} />
              ) : p?.execution_mode === "mcp" ? (
                <>
                  <Plug />
                  <h2>等待外部 Agent 供稿</h2>
                  <button onClick={() => setConnectModal(true)}>
                    连接外部 Agent
                  </button>
                </>
              ) : (
                <>
                  <Clapperboard />
                  <h2>{p ? states[p.status] : "创建第一个项目"}</h2>
                  {!p && (
                    <button className="primary" onClick={() => setModal(true)}>
                      新建项目
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </main>
      </div>
      {trace && p && <Trace p={p} close={() => showTrace(false)} />}
      {cloneTarget && (
        <div className="overlay">
          <form role="dialog" aria-label="克隆转画幅" onSubmit={clone}>
            <header>
              <h2>克隆转画幅</h2>
              <button type="button" onClick={() => setClone(null)}>
                关闭
              </button>
            </header>
            <label>
              项目标题
              <input name="topic" required defaultValue={cloneTarget.topic} />
            </label>
            <label>
              目标画幅
              <select
                name="target_format"
                defaultValue={
                  cloneTarget.target_format === "video_16_9"
                    ? "video_9_16"
                    : "video_16_9"
                }
              >
                {Object.entries(formats).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary">创建副本</button>
          </form>
        </div>
      )}
      {connectModal && p && (
        <EngineConnection
          id={p.id}
          engines={engines}
          close={() => setConnectModal(false)}
        />
      )}
      {modal && (
        <CreateProjectModal
          engines={engines}
          close={() => setModal(false)}
          create={create}
        />
      )}
      {drawer && p && <SourceDrawer p={p} close={() => setDrawer(false)} />}
      {error && (
        <div className="toast" role="alert">
          {error}
          <button onClick={() => fail("")}>关闭</button>
        </div>
      )}
    </div>
  );
}
