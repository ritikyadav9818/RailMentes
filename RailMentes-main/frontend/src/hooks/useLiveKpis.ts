import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import { useHistoryStore } from "../store/useHistoryStore";
import { pollKpis, type KpiPollState } from "../utils/kpiPolling";

/**
 * Live KPIs of the four strategies for the current scenario. Polls GET /kpis (202 = computing) and starts
 * again when the run restarts. Pass `enabled = false` (offline, tab hidden) to stop polling.
 */
export function useLiveKpis(enabled: boolean): { state: KpiPollState; retry: () => void } {
  const runId = useHistoryStore((s) => s.runId);
  const [state, setState] = useState<KpiPollState>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    const abort = new AbortController();
    void pollKpis({ fetchKpis: (signal) => api.kpis(signal), onState: setState, signal: abort.signal });
    return () => abort.abort();
  }, [enabled, runId, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { state, retry };
}
