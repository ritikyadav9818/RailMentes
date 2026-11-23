import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import type { BenchmarkSummary, BenchmarkVariant } from "../api/types";

export type BenchmarkState =
  | { phase: "loading" }
  | { phase: "ready"; summary: BenchmarkSummary }
  | { phase: "error"; message: string; missing: boolean };

/** Loads the saved 20-seed benchmark from the backend; a missing file is reported as such, not as a crash. */
export function useBenchmark(variant: BenchmarkVariant): { state: BenchmarkState; retry: () => void } {
  const [state, setState] = useState<BenchmarkState>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    setState({ phase: "loading" });
    api
      .benchmark(variant, abort.signal)
      .then((summary) => setState({ phase: "ready", summary }))
      .catch((error: unknown) => {
        if (abort.signal.aborted) return;
        const status = error instanceof ApiError ? error.status : null;
        const message = error instanceof ApiError && status === 0 ? "Cannot reach the backend." : error instanceof Error ? error.message : "Could not load the benchmark.";
        setState({ phase: "error", message, missing: status === 404 });
      });
    return () => abort.abort();
  }, [variant, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { state, retry };
}
