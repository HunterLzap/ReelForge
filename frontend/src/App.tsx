import { useEffect, useState } from "react";
import { Toaster } from "sonner";
import { useStudio, report } from "@/store/studioStore";
import { HomeView, CreateDialog } from "./components/HomeView";
import { StudioView } from "./components/StudioView";
import { ModelRouterModal } from "./components/ModelRouterModal";
import { CommandPalette } from "./components/CommandPalette";
import { useShortcut } from "./components/editorPlayback";
import { TooltipProvider } from "./components/ui/tooltip";
import { Dialog } from "./components/ui/dialog";
import { Button } from "./components/ui/button";
import { Input, Field } from "./components/ui/input";
export default function App() {
  const modelCenter = useStudio((s) => s.modelCenter);
  const project = useStudio((s) => s.project);
  const [palette, setPalette] = useState(false),
    [mode, create] = useState<string | null>(null),
    [auth, setAuth] = useState(false),
    [token, setToken] = useState("");
  useEffect(() => {
    const authRequired = () => setAuth(true);
    window.addEventListener("reelforge:auth", authRequired);
    const s = useStudio.getState(),
      pid = new URL(location.href).searchParams.get("project");
    s.refreshHome()
      .then(() => {
        const p = useStudio.getState().projects.find((p) => p.id === pid);
        if (p) void s.open(p);
      })
      .catch(report);
    return () => {
      window.removeEventListener("reelforge:auth", authRequired);
      s.close();
    };
  }, []);
  useShortcut(
    "mod+k",
    () => setPalette((v) => !v),
    !mode && !auth && !modelCenter,
  );
  return (
    <TooltipProvider delayDuration={350}>
      {project ? (
        <StudioView
          palette={() => setPalette(true)}
          shortcuts={!palette && !mode && !auth && !modelCenter}
        />
      ) : (
        <HomeView palette={() => setPalette(true)} create={create} />
      )}
      {modelCenter && <ModelRouterModal />}
      <CommandPalette
        open={palette}
        close={() => setPalette(false)}
        create={create}
      />
      {mode && <CreateDialog mode={mode} close={() => create(null)} />}
      <Dialog open={auth} onOpenChange={setAuth} title="访问工作区">
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            localStorage.setItem("reelforge_token", token.trim());
            location.reload();
          }}
        >
          <Field label="访问令牌">
            <Input
              autoFocus
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </Field>
          <Button type="submit" variant="primary" disabled={!token.trim()}>
            连接工作区
          </Button>
        </form>
      </Dialog>
      <Toaster position="bottom-center" closeButton />
    </TooltipProvider>
  );
}
