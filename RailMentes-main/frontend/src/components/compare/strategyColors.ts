import type { StrategyName } from "../../api/types";

/** One colour per strategy, used in every chart on the Compare tab. */
export const STRATEGY_COLORS: Record<StrategyName, string> = {
  no_control: "#7b8ba1",
  fcfs: "#a78bfa",
  priority: "#e8c468",
  cpsat: "#38bdf8",
};
