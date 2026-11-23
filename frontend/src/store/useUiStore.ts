/** Layout state of the side panels, remembered in localStorage. Kept apart from the data store. */
import { create } from "zustand";

const KEY = "railmentes.ui.v1";
/** Below this window width the alerts panel starts collapsed so the map gets the room. */
const WIDE_SCREEN_PX = 1600;

interface Saved {
  alertsOpen?: boolean;
  trainOpen?: boolean;
}

function load(): Saved {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Saved;
  } catch {
    return {};
  }
}

function save(state: Required<Saved>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // private window or blocked storage: the panels simply are not remembered
  }
}

export type Tab = "map" | "time_distance" | "compare";
export const TABS: { id: Tab; label: string; key: string }[] = [
  { id: "map", label: "Map", key: "1" },
  { id: "time_distance", label: "Time-distance", key: "2" },
  { id: "compare", label: "Compare", key: "3" },
];

/** Disruption kinds the inject dialog supports (shared by the control bar and the command palette). */
export type InjectKind = "fog" | "signal_failure" | "block_closure" | "late_departure";

export interface UiState {
  tab: Tab;
  paletteOpen: boolean;
  helpOpen: boolean;
  injectKind: InjectKind | null;
  setTab: (tab: Tab) => void;
  setPaletteOpen: (open: boolean) => void;
  setHelpOpen: (open: boolean) => void;
  setInjectKind: (kind: InjectKind | null) => void;
  alertsOpen: boolean;
  trainOpen: boolean;
  setAlertsOpen: (open: boolean) => void;
  setTrainOpen: (open: boolean) => void;
  toggleAlerts: () => void;
  toggleTrain: () => void;
}

function initial(): Pick<UiState, "alertsOpen" | "trainOpen"> {
  const saved = load();
  const wide = typeof window !== "undefined" && window.innerWidth >= WIDE_SCREEN_PX;
  return { alertsOpen: saved.alertsOpen ?? wide, trainOpen: saved.trainOpen ?? true };
}

export const useUiStore = create<UiState>()((set, get) => {
  const update = (patch: Partial<Pick<UiState, "alertsOpen" | "trainOpen">>) => {
    set(patch);
    const { alertsOpen, trainOpen } = get();
    save({ alertsOpen, trainOpen });
  };
  return {
    ...initial(),
    tab: "map" as Tab,
    paletteOpen: false,
    helpOpen: false,
    injectKind: null,
    setTab: (tab) => set({ tab }),
    setPaletteOpen: (open) => set({ paletteOpen: open }),
    setHelpOpen: (open) => set({ helpOpen: open }),
    setInjectKind: (kind) => set({ injectKind: kind }),
    setAlertsOpen: (open) => update({ alertsOpen: open }),
    setTrainOpen: (open) => update({ trainOpen: open }),
    toggleAlerts: () => update({ alertsOpen: !get().alertsOpen }),
    toggleTrain: () => update({ trainOpen: !get().trainOpen }),
  };
});
