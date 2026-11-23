import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, X } from "lucide-react";
import { useEffect, useRef } from "react";

import { commitSpeed, pauseSimulation, startSimulation } from "../store/controls";
import { useDemoStore } from "../store/useDemoStore";
import { useRailStore } from "../store/useRailStore";
import { useUiStore } from "../store/useUiStore";
import { DEMO_CAPTIONS, DEMO_SCENARIO, DEMO_SLOW_SPEED, hasProposal } from "../utils/demo";
import { Button } from "./ui/button";

/** Caption card for the guided demo. Feeds snapshots to the demo, and pauses once when the recommendation appears. */
export function DemoCaption() {
  const active = useDemoStore((s) => s.active);
  const current = useDemoStore((s) => s.current);
  const seen = useDemoStore((s) => s.seen.length);
  const end = useDemoStore((s) => s.end);
  const setTab = useUiStore((s) => s.setTab);
  const tab = useUiStore((s) => s.tab);
  /** the demo paused the run and is waiting to see that the recommendation is still there */
  const waiting = useRef(false);

  useEffect(() => {
    if (!active) return;
    waiting.current = false;
    const first = useRailStore.getState().snapshot;
    if (first) useDemoStore.getState().ingest(first);
    return useRailStore.subscribe((s, prev) => {
      const snapshot = s.snapshot;
      if (!snapshot || snapshot === prev.snapshot) return;
      useDemoStore.getState().ingest(snapshot);
      // we paused on a recommendation, but it went away before the pause took effect: carry on until the next one
      if (waiting.current && !snapshot.running) {
        waiting.current = false;
        if (!hasProposal(snapshot)) {
          useDemoStore.getState().rearm("recommendation");
          void startSimulation();
        }
      }
    });
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const running = useRailStore.getState().snapshot?.running;
    if (current === "conflict") {
      useRailStore.getState().updateSettings({ speed: DEMO_SLOW_SPEED });
      void commitSpeed(DEMO_SLOW_SPEED);
    } else if (current === "recommendation" && running) {
      useUiStore.getState().setAlertsOpen(true); // the recommendation lives in the alerts panel
      waiting.current = true;
      void pauseSimulation();
    } else if (current === "applied") {
      useRailStore.getState().updateSettings({ speed: DEMO_SCENARIO.speed });
      void commitSpeed(DEMO_SCENARIO.speed);
    }
  }, [active, current]);

  const caption = DEMO_CAPTIONS[current];
  return (
    <AnimatePresence>
      {active && (tab !== "compare" || current === "finished") && (
        <motion.aside
          key="demo-caption"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          transition={{ duration: 0.25 }}
          className={`glass-strong pointer-events-auto absolute inset-x-0 z-30 mx-auto w-[min(40rem,calc(100%-2rem))] rounded-xl p-4 ${tab === "map" ? "bottom-4" : "bottom-20"}`}
          role="status"
          aria-live="polite"
          aria-label="Guided demo caption"
        >
          <div className="flex items-start gap-3">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <h2 className="text-body font-semibold text-text">{caption.title}</h2>
              <p className="mt-1 text-body text-muted">{caption.body}</p>
              {current === "finished" && (
                <Button size="sm" className="mt-3" onClick={() => setTab("compare")}>
                  Open the Compare tab
                </Button>
              )}
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2">
              <button type="button" onClick={end} aria-label="End the guided demo" className="rounded p-0.5 text-muted hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70">
                <X className="h-4 w-4" />
              </button>
              <span className="font-mono text-micro tracking-normal text-muted">{seen}/5</span>
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
