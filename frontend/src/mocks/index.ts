import type { NetworkInfo, StateSnapshot } from "../api/types";
import networkJson from "./network.json";
import snapshotJson from "./snapshot.json";

/** Realistic mock frame so the UI can be built (and demoed offline) before the backend exists. */
export const mockSnapshot = snapshotJson as StateSnapshot;

/** The fictional corridor, as GET /network returns it. Used when the backend is unreachable. */
export const mockNetwork = networkJson as NetworkInfo;
