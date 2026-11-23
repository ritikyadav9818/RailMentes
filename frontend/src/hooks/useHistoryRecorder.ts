import { useEffect } from "react";

import { useHistoryStore } from "../store/useHistoryStore";
import { useRailStore } from "../store/useRailStore";

/** Feeds every new snapshot into the history store, whichever tab is showing. Mount once at the app root. */
export function useHistoryRecorder(): void {
  useEffect(() => {
    const record = (): void => {
      const { snapshot, network, dataSource } = useRailStore.getState();
      if (snapshot && network) useHistoryStore.getState().ingest(snapshot, network, dataSource);
    };
    record();
    return useRailStore.subscribe((s, prev) => {
      if (s.snapshot !== prev.snapshot || s.network !== prev.network) record();
    });
  }, []);
}
