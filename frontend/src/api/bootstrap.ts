/** Wires the REST client and the WebSocket into the store. Call once from the app root. */
import { useRailStore } from "../store/useRailStore";
import { api } from "./client";
import { wsUrl } from "./config";
import { StateSocket } from "./socket";

/** If the backend neither answers nor refuses within this time, show the demo data. */
export const CONNECT_TIMEOUT_MS = 4000;

async function loadNetwork(signal: AbortSignal): Promise<void> {
  const store = useRailStore.getState();
  if (store.networkSource === "live") return;
  try {
    store.setNetwork(await api.network(signal), "live");
  } catch {
    // not reachable yet: the mock network is installed together with the mock snapshot
  }
}

async function loadScenario(signal: AbortSignal): Promise<void> {
  try {
    const info = await api.scenario(signal);
    const snapshot = useRailStore.getState().snapshot;
    useRailStore.getState().syncScenario(info, snapshot?.strategy ?? "no_control");
  } catch {
    // keep the defaults
  }
}

/** Starts everything; returns a function that stops it. */
export function connectLive(): () => void {
  const abort = new AbortController();
  let synced = false;

  const socket = new StateSocket(wsUrl(), {
    onStatus: (status, attempt) => useRailStore.getState().setSocketStatus(status, attempt),
    onSnapshot: (snapshot) => {
      const store = useRailStore.getState();
      store.applySnapshot(snapshot, "live");
      if (!synced) {
        synced = true;
        void loadNetwork(abort.signal);
        void loadScenario(abort.signal);
      }
    },
  });

  void loadNetwork(abort.signal);
  // started on the next tick: React StrictMode (dev) mounts, unmounts and mounts again, and a
  // socket closed while still connecting makes the browser log a warning
  const starter = setTimeout(() => socket.start(), 0);
  const timeout = setTimeout(() => {
    if (useRailStore.getState().snapshot === null) useRailStore.getState().showMockData();
  }, CONNECT_TIMEOUT_MS);

  return () => {
    clearTimeout(starter);
    clearTimeout(timeout);
    abort.abort();
    socket.stop();
  };
}
