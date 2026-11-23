import type { TrainState } from "../../api/types";
import { DELAY_LABELS, delayColor, delayLevel, formatDelay } from "../../utils/delay";
import { CATEGORY_LABELS } from "../../utils/labels";

/** Small glass card that follows the pointer while it is over a train. */
export function TrainTooltip({ train, x, y }: { train: TrainState; x: number; y: number }) {
  return (
    <div
      role="tooltip"
      className="glass-strong pointer-events-none absolute z-20 min-w-[11rem] -translate-y-full rounded-lg px-3 py-2 text-caption"
      style={{ left: x + 16, top: y - 12 }}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-body font-semibold text-text">{train.id}</span>
        <span className="text-muted">{CATEGORY_LABELS[train.category]}</span>
      </div>
      <div className="mt-0.5 truncate text-muted">{train.name}</div>
      <div className="mt-1.5 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ background: delayColor(train.delay_min), boxShadow: `0 0 8px ${delayColor(train.delay_min)}` }} />
        <span className="font-mono text-text">{formatDelay(train.delay_min)}</span>
        <span className="text-muted">{DELAY_LABELS[delayLevel(train.delay_min)]}</span>
      </div>
    </div>
  );
}
