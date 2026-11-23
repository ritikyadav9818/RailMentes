/** State of the guided demo (see utils/demo.ts). Not remembered between page loads. */
import { create } from "zustand";

import type { StateSnapshot } from "../api/types";
import { DEMO_IDLE, advanceDemo, rearm, type DemoEvent, type DemoState } from "../utils/demo";

interface DemoStore extends DemoState {
  begin: () => void;
  end: () => void;
  ingest: (snapshot: StateSnapshot) => void;
  /** show an event's caption again the next time it happens */
  rearm: (event: DemoEvent) => void;
}

export const useDemoStore = create<DemoStore>()((set, get) => ({
  ...DEMO_IDLE,
  begin: () => set({ active: true, seen: [], current: "intro" }),
  end: () => set({ ...DEMO_IDLE }),
  rearm: (event) => {
    const { active, seen, current } = get();
    const next = rearm({ active, seen, current }, event);
    set({ seen: next.seen, current: next.current });
  },
  ingest: (snapshot) => {
    const { active, seen, current } = get();
    const next = advanceDemo({ active, seen, current }, snapshot);
    if (next.current !== current || next.seen.length !== seen.length) set({ seen: next.seen, current: next.current });
  },
}));
