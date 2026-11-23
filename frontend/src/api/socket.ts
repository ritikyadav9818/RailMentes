/** WebSocket client for /ws/state with automatic reconnect and exponential backoff. */
import type { StateSnapshot, WsMessage } from "./types";

export type SocketStatus = "connecting" | "open" | "reconnecting" | "closed";

export const BACKOFF_START_MS = 1000;
export const BACKOFF_MAX_MS = 15000;

/** Delay before reconnect attempt number `attempt` (0-based): 1 s, 2 s, 4 s ... capped at 15 s. */
export function backoffDelay(attempt: number): number {
  return Math.min(BACKOFF_MAX_MS, BACKOFF_START_MS * 2 ** Math.max(0, attempt));
}

/** Parse one frame; returns null for anything that is not a known message. */
export function parseMessage(raw: unknown): WsMessage | null {
  if (typeof raw !== "string") return null;
  try {
    const msg = JSON.parse(raw) as Partial<WsMessage> | null;
    if (!msg || typeof msg !== "object" || typeof msg.type !== "string") return null;
    if (msg.type === "hello" || msg.type === "snapshot" || msg.type === "error") return msg as WsMessage;
    return null;
  } catch {
    return null;
  }
}

export interface SocketHandlers {
  onSnapshot: (snapshot: StateSnapshot) => void;
  /** `attempt` = number of failed connection attempts since the last good frame */
  onStatus: (status: SocketStatus, attempt: number) => void;
}

/** The browser pieces, injectable so tests can run without a real socket or real timers. */
export interface SocketDeps {
  createSocket: (url: string) => WebSocket;
  setTimer: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>;
  clearTimer: (id: ReturnType<typeof setTimeout>) => void;
}

const browserDeps: SocketDeps = {
  createSocket: (url) => new WebSocket(url),
  setTimer: (fn, ms) => setTimeout(fn, ms),
  clearTimer: (id) => clearTimeout(id),
};

export class StateSocket {
  private ws: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private stopped = true;

  constructor(
    private readonly url: string,
    private readonly handlers: SocketHandlers,
    private readonly deps: SocketDeps = browserDeps,
  ) {}

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempt = 0;
    this.open();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) this.deps.clearTimer(this.timer);
    this.timer = null;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null;
      ws.close();
    }
    this.handlers.onStatus("closed", this.attempt);
  }

  private open(): void {
    this.handlers.onStatus(this.attempt === 0 ? "connecting" : "reconnecting", this.attempt);
    let ws: WebSocket;
    try {
      ws = this.deps.createSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => this.handlers.onStatus("open", this.attempt);
    ws.onmessage = (ev) => {
      const msg = parseMessage(ev.data);
      if (msg?.type !== "snapshot") return;
      this.attempt = 0; // a working connection resets the backoff
      this.handlers.onSnapshot(msg.data);
    };
    ws.onclose = () => {
      this.ws = null;
      if (!this.stopped) this.scheduleReconnect();
    };
    ws.onerror = () => {
      // a close event always follows; reconnecting is handled there
    };
  }

  private scheduleReconnect(): void {
    const wait = backoffDelay(this.attempt);
    this.attempt += 1;
    this.handlers.onStatus("reconnecting", this.attempt);
    this.timer = this.deps.setTimer(() => {
      this.timer = null;
      if (!this.stopped) this.open();
    }, wait);
  }
}
