import { useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { TrainExplanation } from "../api/types";

export type ExplanationState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: TrainExplanation }
  | { status: "error"; message: string; code: number };

/**
 * Loads GET /trains/{id}/explanation. The model is asked only when the train, the horizon or the
 * train's next station changes (the backend computes it on request, never per tick).
 * `enabled` is false for offline demo data.
 */
export function useExplanation(trainId: string | null, horizon: number, nextStation: string | null, enabled: boolean) {
  const [state, setState] = useState<ExplanationState>({ status: "idle" });
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    if (!trainId || !enabled) {
      setState({ status: "idle" });
      return;
    }
    const abort = new AbortController();
    setState((prev) => (prev.status === "ready" && prev.data.train_id === trainId ? prev : { status: "loading" }));
    api
      .explanation(trainId, horizon, 6, abort.signal)
      .then((data) => setState({ status: "ready", data }))
      .catch((err: unknown) => {
        if (abort.signal.aborted) return;
        const code = err instanceof ApiError ? err.status : 0;
        setState({ status: "error", code, message: err instanceof Error ? err.message : "Could not load the explanation" });
      });
    return () => abort.abort();
  }, [trainId, horizon, nextStation, enabled, refresh]);

  return { state, reload: () => setRefresh((n) => n + 1) };
}
