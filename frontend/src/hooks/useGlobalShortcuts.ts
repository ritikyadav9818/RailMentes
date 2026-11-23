import { useEffect } from "react";

import { pauseSimulation, startSimulation } from "../store/controls";
import { useRailStore } from "../store/useRailStore";
import { useUiStore, type Tab } from "../store/useUiStore";
import { ignoreShortcut } from "../utils/keys";

const TAB_KEYS: Record<string, Tab> = { "1": "map", "2": "time_distance", "3": "compare" };

/** True if Space would also "press" the focused control (a button, link, tab, checkbox ...). */
function spaceBelongsToControl(e: KeyboardEvent): boolean {
  const el = e.target instanceof HTMLElement ? e.target : null;
  return el !== null && (["BUTTON", "A", "SUMMARY"].includes(el.tagName) || el.getAttribute("role") === "tab");
}

/**
 * App-wide keys: Ctrl+K palette, ? help, 1 / 2 / 3 tabs, Space start or pause.
 * Panel keys ( [ and ] ) and the map keys are handled where those features live.
 */
export function useGlobalShortcuts(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const ui = useUiStore.getState();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ui.setPaletteOpen(!ui.paletteOpen);
        return;
      }
      if (ignoreShortcut(e)) return;
      if (e.key === "?") ui.setHelpOpen(true);
      else if (TAB_KEYS[e.key]) ui.setTab(TAB_KEYS[e.key]);
      else if (e.key === " " && !spaceBelongsToControl(e)) {
        const { snapshot, dataSource } = useRailStore.getState();
        if (dataSource !== "live") return;
        e.preventDefault();
        void (snapshot?.running ? pauseSimulation() : startSimulation());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
