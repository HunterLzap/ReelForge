import { ArrowLeft, Undo2, Redo2, Download } from "lucide-react";
import { useStudio, report } from "@/store/studioStore";
import { Button } from "./ui/button";
import { Tooltip } from "./ui/tooltip";
import { CommandButton, StoragePill } from "./StudioControls";
import { stageNames } from "./HomeView";
import { PlanStage } from "./PlanStage";
import { lazy, Suspense } from "react";
import { DeliveryStage } from "./DeliveryStage";
import { useShortcut } from "./editorPlayback";
import type { Stage } from "@/types";
const EditStage = lazy(() =>
  import("./EditStage").then((module) => ({ default: module.EditStage })),
);
export function StudioView({
  palette,
  shortcuts,
}: {
  palette: () => void;
  shortcuts: boolean;
}) {
  const {
    project,
    timeline,
    stage,
    setStage,
    close,
    refreshHome,
    undo,
    redo,
    busy,
  } = useStudio();
  useShortcut("mod+z", () => void undo(), shortcuts && !busy);
  useShortcut("mod+shift+z", () => void redo(), shortcuts && !busy);
  return (
    <div className="studio">
      <header className="topbar">
        <Button
          variant="ghost"
          onClick={() => {
            close();
            void refreshHome().catch(report);
          }}
        >
          <ArrowLeft />
          作品
        </Button>
        <strong title={project?.topic}>{project?.topic}</strong>
        <nav className="stepper" aria-label="工作阶段">
          {(Object.keys(stageNames) as Stage[]).map((s) => (
            <button
              key={s}
              aria-current={stage === s ? "step" : undefined}
              onClick={() => setStage(s)}
            >
              {stageNames[s]}
            </button>
          ))}
        </nav>
        <div className="row top-actions">
          <Tooltip label="撤销 · Ctrl / ⌘ Z">
            <Button
              aria-label="撤销"
              disabled={busy || !timeline?.revision}
              onClick={undo}
            >
              <Undo2 />
            </Button>
          </Tooltip>
          <Tooltip label="重做 · Ctrl / ⌘ Shift Z">
            <Button aria-label="重做" disabled={busy} onClick={redo}>
              <Redo2 />
            </Button>
          </Tooltip>
          <Button onClick={() => useStudio.getState().showModels("models")}>
            模型
          </Button>
          <StoragePill />
          <CommandButton open={palette} />
          <Button variant="primary" onClick={() => setStage("delivery")}>
            <Download />
            导出交付
          </Button>
        </div>
      </header>
      {!timeline ? (
        <p className="empty">正在载入时间轴…</p>
      ) : stage === "plan" ? (
        <PlanStage />
      ) : stage === "edit" ? (
        <Suspense fallback={<p className="empty">正在载入剪辑台…</p>}>
          <EditStage shortcuts={shortcuts} />
        </Suspense>
      ) : (
        <DeliveryStage />
      )}
    </div>
  );
}
