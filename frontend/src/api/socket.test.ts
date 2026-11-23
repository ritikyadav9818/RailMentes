import { describe, expect, it } from "vitest";

import { mockSnapshot } from "../mocks";
import { StateSocket, backoffDelay, parseMessage, type SocketDeps, type SocketStatus } from "./socket";
import { detailMessage } from "./client";
import { wsUrl } from "./config";

describe("backoffDelay", () => {
  it("doubles from 1 s and stops at 15 s", () => {
    expect([0, 1, 2, 3, 4, 5, 10].map(backoffDelay)).toEqual([1000, 2000, 4000, 8000, 15000, 15000, 15000]);
  });
});

describe("parseMessage", () => {
  it("accepts the three message types and rejects the rest", () => {
    expect(parseMessage(JSON.stringify({ type: "hello", seq: 0, data: {} }))?.type).toBe("hello");
    expect(parseMessage(JSON.stringify({ type: "snapshot", seq: 1, data: mockSnapshot }))?.type).toBe("snapshot");
    expect(parseMessage(JSON.stringify({ type: "weird" }))).toBeNull();
    expect(parseMessage("not json")).toBeNull();
    expect(parseMessage(42)).toBeNull();
  });
});

describe("urls and error text", () => {
  it("derives the WebSocket URL from the API URL", () => {
    expect(wsUrl("http://localhost:8000")).toBe("ws://localhost:8000/ws/state");
    expect(wsUrl("https://example.org/")).toBe("wss://example.org/ws/state");
  });

  it("reads FastAPI error bodies", () => {
    expect(detailMessage({ detail: "Train is unknown" }, "x")).toBe("Train is unknown");
    expect(detailMessage({ detail: [{ msg: "bad speed" }, { msg: "bad seed" }] }, "x")).toBe("bad speed; bad seed");
    expect(detailMessage(null, "fallback")).toBe("fallback");
  });
});

/** A hand-driven fake WebSocket and clock. */
function fakeWorld() {
  const sockets: FakeSocket[] = [];
  const timers: { fn: () => void; ms: number; id: number }[] = [];
  let nextId = 1;
  class FakeSocket {
    onopen: (() => void) | null = null;
    onmessage: ((e: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    closed = false;
    close() {
      this.closed = true;
    }
  }
  const deps: SocketDeps = {
    createSocket: () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s as unknown as WebSocket;
    },
    setTimer: (fn, ms) => {
      const id = nextId++;
      timers.push({ fn, ms, id });
      return id as unknown as ReturnType<typeof setTimeout>;
    },
    clearTimer: (id) => {
      const i = timers.findIndex((t) => t.id === (id as unknown as number));
      if (i >= 0) timers.splice(i, 1);
    },
  };
  return { sockets, timers, deps };
}

describe("StateSocket", () => {
  it("reconnects with growing delays and resets the delay after a good frame", () => {
    const { sockets, timers, deps } = fakeWorld();
    const statuses: [SocketStatus, number][] = [];
    const snaps: number[] = [];
    const socket = new StateSocket("ws://x", { onStatus: (s, a) => statuses.push([s, a]), onSnapshot: (d) => snaps.push(d.tick) }, deps);
    socket.start();
    expect(statuses[0]).toEqual(["connecting", 0]);

    // three failures in a row: 1 s, 2 s, 4 s
    for (const expected of [1000, 2000, 4000]) {
      sockets[sockets.length - 1].onclose?.();
      expect(timers[timers.length - 1].ms).toBe(expected);
      timers[timers.length - 1].fn();
    }
    expect(sockets).toHaveLength(4);
    expect(statuses.some(([s, a]) => s === "reconnecting" && a === 3)).toBe(true);

    // a good frame resets the backoff
    const live = sockets[sockets.length - 1];
    live.onmessage?.({ data: JSON.stringify({ type: "snapshot", seq: 1, data: { ...mockSnapshot, tick: 5 } }) });
    expect(snaps).toEqual([5]);
    live.onclose?.();
    expect(timers[timers.length - 1].ms).toBe(1000);
  });

  it("ignores hello and garbage frames", () => {
    const { sockets, deps } = fakeWorld();
    const snaps: number[] = [];
    new StateSocket("ws://x", { onStatus: () => {}, onSnapshot: (d) => snaps.push(d.tick) }, deps).start();
    sockets[0].onmessage?.({ data: JSON.stringify({ type: "hello", seq: 0, data: {} }) });
    sockets[0].onmessage?.({ data: "{{{" });
    expect(snaps).toEqual([]);
  });

  it("stop() closes the socket and cancels a pending reconnect", () => {
    const { sockets, timers, deps } = fakeWorld();
    const socket = new StateSocket("ws://x", { onStatus: () => {}, onSnapshot: () => {} }, deps);
    socket.start();
    sockets[0].onclose?.();
    expect(timers).toHaveLength(1);
    socket.stop();
    expect(timers).toHaveLength(0);
    expect(sockets).toHaveLength(1);
  });
});
