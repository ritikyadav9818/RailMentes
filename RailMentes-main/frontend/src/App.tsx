import { MotionConfig, motion } from "framer-motion";
import { Suspense, lazy, useEffect } from "react";

import { connectLive } from "./api/bootstrap";
import { AlertsPanel } from "./components/AlertsFeed";
import { CommandPalette } from "./components/CommandPalette";
import { DemoCaption } from "./components/DemoCaption";
import { DisruptionStrip } from "./components/DisruptionStrip";
import { Header } from "./components/Header";
import { HelpDialog } from "./components/HelpDialog";
import { KpiStrip } from "./components/KpiStrip";
import { NetworkMap } from "./components/map/NetworkMap";
import { TabBar, panelId, tabId } from "./components/TabBar";
import { TrainDrawer } from "./components/TrainDrawer";
import { Toaster } from "./components/ui/sonner";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { useHistoryRecorder } from "./hooks/useHistoryRecorder";
import { useUiStore } from "./store/useUiStore";
import { ignoreShortcut } from "./utils/keys";

/** Panel shortcuts: [ toggles the alerts panel, ] the train panel. Map shortcuts live in the map. */
function usePanelShortcuts(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (ignoreShortcut(e)) return;
      if (e.key === "[") useUiStore.getState().toggleAlerts();
      else if (e.key === "]") useUiStore.getState().toggleTrain();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

// the two chart views bring D3 and Recharts with them, so they load only when first opened
const ComparePage = lazy(() => import("./components/compare/ComparePage").then((m) => ({ default: m.ComparePage })));
const TimeDistanceGraph = lazy(() => import("./components/timedistance/TimeDistanceGraph").then((m) => ({ default: m.TimeDistanceGraph })));

function ViewFallback() {
  return (
    <div className="grid h-full place-items-center" aria-busy="true" role="status" aria-label="Loading view">
      <div className="h-3/4 w-11/12 animate-pulse rounded-lg bg-white/[0.04]" />
    </div>
  );
}

const PANEL = "relative min-w-0 flex-1 overflow-hidden rounded-xl border border-white/[0.08] shadow-glass";

/**
 * Live controller dashboard. Three views share the header, the alerts panel, the train panel and the KPI
 * chips: the map (the hero), the time-distance graph and the strategy comparison. The map stays mounted
 * (hidden) when another view is open, so its zoom and the live connection are never torn down.
 */
export default function App() {
  useEffect(() => connectLive(), []);
  usePanelShortcuts();
  useGlobalShortcuts();
  useHistoryRecorder();
  const tab = useUiStore((s) => s.tab);

  return (
    // reducedMotion="user": Framer Motion skips transform animations when the OS asks for less motion
    <MotionConfig reducedMotion="user">
      <div className="flex h-full min-h-0 flex-col">
        <motion.div initial={{ opacity: 0, y: -14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}>
          <Header />
        </motion.div>
        <TabBar />
        <main className="flex min-h-0 flex-1 gap-2 p-2">
          <AlertsPanel />
          <motion.section
            className={PANEL}
            aria-label="Main view"
            initial={{ opacity: 0, scale: 0.985 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          >
            <div id={panelId("map")} role="tabpanel" aria-labelledby={tabId("map")} hidden={tab !== "map"} className="absolute inset-0">
              <NetworkMap />
            </div>
            {tab === "map" ? (
              // floating chips: KPIs on top, active disruptions in a row under them, so they can never collide
              <div className="pointer-events-none absolute inset-x-3 top-3 flex flex-col items-start gap-2">
                <KpiStrip />
                <DisruptionStrip />
              </div>
            ) : (
              <div className="absolute inset-0 flex flex-col">
                <div className="flex flex-wrap items-start gap-2 p-3 pb-0">
                  <KpiStrip />
                  <DisruptionStrip />
                </div>
                <div
                  id={panelId(tab)}
                  role="tabpanel"
                  aria-labelledby={tabId(tab)}
                  className="min-h-0 flex-1"
                >
                  <Suspense fallback={<ViewFallback />}>{tab === "time_distance" ? <TimeDistanceGraph /> : <ComparePage />}</Suspense>
                </div>
              </div>
            )}
            <DemoCaption />
          </motion.section>
          {tab !== "compare" && <TrainDrawer />}
        </main>
        <CommandPalette />
        <HelpDialog />
        <Toaster />
      </div>
    </MotionConfig>
  );
}
