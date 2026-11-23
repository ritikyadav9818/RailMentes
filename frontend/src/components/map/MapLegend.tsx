import { Info } from "lucide-react";
import { useState } from "react";

import { DELAY_COLORS, DELAY_LABELS, type DelayLevel } from "../../utils/delay";
import { TrainShape } from "./TrainShape";

const LEVELS: DelayLevel[] = ["on_time", "minor", "major", "severe"];

function Swatch({ children }: { children: React.ReactNode }) {
  return (
    <svg width="16" height="16" viewBox="-14 -14 28 28" aria-hidden="true" className="shrink-0">
      {children}
    </svg>
  );
}

/** Key to colours, marker shapes and track types. Colours always show; the rest opens on demand. */
export function MapLegend() {
  const [open, setOpen] = useState(false);
  return (
    <div className="glass-strong max-w-full rounded-lg px-2.5 py-1.5 text-caption text-muted">
      <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1">
        {LEVELS.map((l) => (
          <span key={l} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: DELAY_COLORS[l], boxShadow: `0 0 8px ${DELAY_COLORS[l]}88` }} />
            {DELAY_LABELS[l].replace(" delay", "")}
          </span>
        ))}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex items-center gap-1 rounded px-1 text-muted transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70"
        >
          <Info className="h-3.5 w-3.5" /> {open ? "Less" : "Key"}
        </button>
      </div>
      {open && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3.5 gap-y-1 border-t border-white/10 pt-1.5">
          <span className="flex items-center gap-1"><Swatch><TrainShape category="premium" color="#8a9bb0" /></Swatch>Premium</span>
          <span className="flex items-center gap-1"><Swatch><TrainShape category="express" color="#8a9bb0" /></Swatch>Express</span>
          <span className="flex items-center gap-1"><Swatch><TrainShape category="passenger" color="#8a9bb0" /></Swatch>Passenger</span>
          <span className="flex items-center gap-1"><Swatch><TrainShape category="freight" color="#8a9bb0" /></Swatch>Freight</span>
          <span className="flex items-center gap-1">
            <svg width="22" height="10" aria-hidden="true"><line x1="0" y1="5" x2="22" y2="5" stroke="#5f7b9b" strokeWidth="5" /></svg>
            Single line
          </span>
          <span className="flex items-center gap-1">
            <svg width="22" height="10" aria-hidden="true">
              <line x1="0" y1="2" x2="22" y2="2" stroke="#4a627d" strokeWidth="2.4" />
              <line x1="0" y1="8" x2="22" y2="8" stroke="#4a627d" strokeWidth="2.4" />
            </svg>
            Double line
          </span>
        </div>
      )}
    </div>
  );
}
