import { Command } from "cmdk";
import { Search } from "lucide-react";
import { useStudio } from "@/store/studioStore";
import { modes } from "@/studio";
import { Dialog } from "./ui/dialog";
import { stageNames } from "./HomeView";
import type { Stage } from "@/types";
export function CommandPalette({
  open,
  close,
  create,
}: {
  open: boolean;
  close: () => void;
  create: (id: string) => void;
}) {
  const s = useStudio();
  const action = (fn: () => void) => () => {
    close();
    fn();
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) close();
      }}
      title="命令面板"
    >
      <Command label="命令面板">
        <div className="command-search">
          <Search />
          <Command.Input autoFocus placeholder="搜索作品、模式或操作…" />
        </div>
        <Command.List>
          <Command.Empty>没有匹配的命令</Command.Empty>
          {s.project && (
            <Command.Group heading="当前作品">
              {(Object.keys(stageNames) as Stage[]).map((k) => (
                <Command.Item key={k} onSelect={action(() => s.setStage(k))}>
                  {stageNames[k]}
                </Command.Item>
              ))}
              <Command.Item onSelect={action(s.undo)}>撤销编辑</Command.Item>
              <Command.Item onSelect={action(s.redo)}>重做编辑</Command.Item>
              <Command.Item
                onSelect={action(() => {
                  s.close();
                  void s.refreshHome();
                })}
              >
                返回作品
              </Command.Item>
            </Command.Group>
          )}
          <Command.Group heading="新建作品">
            {modes.map((m) => (
              <Command.Item key={m.id} onSelect={action(() => create(m.id))}>
                {m.name}
              </Command.Item>
            ))}
          </Command.Group>
          <Command.Group heading="最近作品">
            {s.projects.map((p) => (
              <Command.Item
                key={p.id}
                value={p.topic + " " + p.id}
                onSelect={action(() => void s.open(p))}
              >
                {p.topic}
              </Command.Item>
            ))}
          </Command.Group>
        </Command.List>
      </Command>
    </Dialog>
  );
}
