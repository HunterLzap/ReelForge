import { create } from "zustand";
import type { PlayerRef } from "@remotion/player";
import { useHotkeys } from "react-hotkeys-hook";
import type { RefObject } from "react";
export type PlayerHandle = RefObject<PlayerRef | null>;
export const usePlayback = create<{ frame: number; playing: boolean }>(() => ({
  frame: 0,
  playing: false,
}));
export function seek(player: PlayerHandle, ms: number, fps: number) {
  player.current?.pause();
  player.current?.seekTo(Math.max(0, Math.round((ms * fps) / 1000)));
}
export function useShortcut(keys: string, action: () => void, enabled = true) {
  useHotkeys(
    keys,
    (e) => {
      if (
        e.repeat ||
        (e.target instanceof Element &&
          e.target.closest(
            "input,textarea,select,[contenteditable=true],[role=combobox],[role=listbox]",
          ))
      )
        return;
      e.preventDefault();
      action();
    },
    { enabled, enableOnFormTags: false, enableOnContentEditable: false },
    [action, enabled],
  );
}
