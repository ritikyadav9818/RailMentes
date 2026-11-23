/** The command palette's actions: what exists, when it is available, and how a typed query finds it. */
import type { StrategyName } from "../api/types";
import type { InjectKind, Tab } from "../store/useUiStore";
import { DISRUPTION_LABELS, STRATEGY_LABELS } from "./labels";

export type CommandSection = "Simulation" | "Strategy" | "Disruption" | "View" | "Demo" | "Help";

export interface Command {
  id: string;
  title: string;
  section: CommandSection;
  /** extra words that should find this command */
  keywords: string[];
  shortcut?: string;
  enabled: boolean;
  run: () => void;
}

/** Everything a command can do; wired to the real stores in CommandPalette, replaced by spies in tests. */
export interface CommandActions {
  start: () => void;
  pause: () => void;
  reset: () => void;
  setStrategy: (strategy: StrategyName) => void;
  inject: (kind: InjectKind) => void;
  setTab: (tab: Tab) => void;
  replay: (strategy: StrategyName) => void;
  demo: () => void;
  openHelp: () => void;
  toggleAlerts: () => void;
  toggleTrain: () => void;
}

export interface CommandContext {
  /** backend reachable: simulation commands need it */
  live: boolean;
  running: boolean;
  strategy: StrategyName;
  actions: CommandActions;
}

export const STRATEGIES: StrategyName[] = ["no_control", "fcfs", "priority", "cpsat"];
export const INJECTABLE_KINDS: InjectKind[] = ["fog", "signal_failure", "block_closure", "late_departure"];
const TAB_TITLES: Record<Tab, string> = { map: "Map", time_distance: "Time-distance graph", compare: "Compare strategies" };
const TAB_KEYS: Record<Tab, string> = { map: "1", time_distance: "2", compare: "3" };

export function buildCommands(ctx: CommandContext): Command[] {
  const { live, running, strategy, actions } = ctx;
  const list: Command[] = [
    ctx.running
      ? { id: "sim.pause", title: "Pause the simulation", section: "Simulation", keywords: ["stop", "halt"], shortcut: "Space", enabled: live, run: actions.pause }
      : { id: "sim.start", title: "Start the simulation", section: "Simulation", keywords: ["run", "play", "resume"], shortcut: "Space", enabled: live, run: actions.start },
    { id: "sim.reset", title: "Reset the day", section: "Simulation", keywords: ["restart", "rewind"], enabled: live, run: actions.reset },
  ];
  for (const s of STRATEGIES) {
    list.push({
      id: `strategy.${s}`,
      title: `Switch strategy to ${STRATEGY_LABELS[s]}`,
      section: "Strategy",
      keywords: ["strategy", "control", "optimizer", s.replace("_", " ")],
      enabled: live && s !== strategy,
      run: () => actions.setStrategy(s),
    });
  }
  for (const s of STRATEGIES) {
    list.push({
      id: `replay.${s}`,
      title: `Replay the same day with ${STRATEGY_LABELS[s]}`,
      section: "Strategy",
      keywords: ["replay", "again", "same scenario", "compare", s.replace("_", " ")],
      enabled: live && s !== strategy,
      run: () => actions.replay(s),
    });
  }
  for (const k of INJECTABLE_KINDS) {
    list.push({
      id: `inject.${k}`,
      title: `Inject disruption: ${DISRUPTION_LABELS[k]}`,
      section: "Disruption",
      keywords: ["inject", "disruption", "add", k.replace("_", " ")],
      enabled: live,
      run: () => actions.inject(k),
    });
  }
  for (const t of ["map", "time_distance", "compare"] as Tab[]) {
    list.push({
      id: `tab.${t}`,
      title: `Go to ${TAB_TITLES[t]}`,
      section: "View",
      keywords: ["tab", "view", "show", t.replace("_", " "), t === "time_distance" ? "string graph" : t === "compare" ? "kpi benchmark results" : "network"],
      shortcut: TAB_KEYS[t],
      enabled: true,
      run: () => actions.setTab(t),
    });
  }
  list.push(
    { id: "view.alerts", title: "Show or hide the alerts panel", section: "View", keywords: ["alerts", "panel", "recommendations"], shortcut: "[", enabled: true, run: actions.toggleAlerts },
    { id: "view.train", title: "Show or hide the train panel", section: "View", keywords: ["train", "drawer", "panel"], shortcut: "]", enabled: true, run: actions.toggleTrain },
    { id: "demo.start", title: "Start the guided demo", section: "Demo", keywords: ["demo", "tour", "story", "guided"], enabled: live, run: actions.demo },
    { id: "help.shortcuts", title: "Keyboard shortcuts", section: "Help", keywords: ["help", "keys", "shortcuts"], shortcut: "?", enabled: true, run: actions.openHelp },
  );
  void running;
  return list;
}

/** Commands whose title, section or keywords contain every word of the query; best matches first. Empty query = all. */
export function filterCommands(commands: Command[], query: string): Command[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return commands;
  const scored: { cmd: Command; score: number }[] = [];
  for (const cmd of commands) {
    const title = cmd.title.toLowerCase();
    const haystack = `${title} ${cmd.section.toLowerCase()} ${cmd.keywords.join(" ").toLowerCase()}`;
    if (!words.every((w) => haystack.includes(w))) continue;
    const score = words.reduce((sum, w) => sum + (title.startsWith(w) ? 3 : title.includes(w) ? 2 : 1), 0) - (cmd.enabled ? 0 : 10);
    scored.push({ cmd, score });
  }
  return scored.sort((a, b) => b.score - a.score).map((s) => s.cmd);
}
