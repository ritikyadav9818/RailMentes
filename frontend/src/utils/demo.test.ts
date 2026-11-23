import { describe, expect, it } from "vitest";

import { mockSnapshot } from "../mocks";
import { DEMO_CAPTIONS, DEMO_IDLE, DEMO_SCENARIO, DEMO_SLOW_SPEED, advanceDemo, eventsIn, hasProposal, rearm, type DemoState } from "./demo";

const empty = { ...mockSnapshot, disruptions: [], conflicts: [], recommendations: [] };
const active: DemoState = { ...DEMO_IDLE, active: true };
const fog = { ...mockSnapshot.disruptions[0], kind: "fog" as const };
const meeting = { ...mockSnapshot.conflicts[0], kind: "single_line_meeting" as const };
const recommendation = mockSnapshot.recommendations[0];

describe("demo scenario", () => {
  it("uses a valid, fixed setup", () => {
    expect(DEMO_SCENARIO.seed).toBe(222);
    expect(DEMO_SCENARIO.speed).toBeGreaterThanOrEqual(0.5);
    expect(DEMO_SCENARIO.speed).toBeLessThanOrEqual(20);
  });

  it("has a caption for every step", () => {
    for (const step of ["intro", "fog", "conflict", "recommendation", "applied", "finished"] as const) {
      expect(DEMO_CAPTIONS[step].title.length).toBeGreaterThan(0);
    }
  });

  it("warns that the saving is a prediction", () => {
    expect(DEMO_CAPTIONS.recommendation.body).toMatch(/prediction/i);
  });
});

describe("eventsIn", () => {
  it("finds nothing in a quiet snapshot", () => {
    expect(eventsIn({ ...empty, trains: empty.trains.map((t) => ({ ...t, status: "running" as const })) }).size).toBe(0);
  });

  it("recognises fog, a single-line meeting, a proposed and an applied recommendation", () => {
    expect(eventsIn({ ...empty, disruptions: [fog] }).has("fog")).toBe(true);
    expect(eventsIn({ ...empty, conflicts: [meeting] }).has("conflict")).toBe(true);
    expect(eventsIn({ ...empty, recommendations: [{ ...recommendation, status: "proposed" }] }).has("recommendation")).toBe(true);
    expect(eventsIn({ ...empty, recommendations: [{ ...recommendation, status: "applied" }] }).has("applied")).toBe(true);
  });

  it("does not count other conflict kinds or disruptions", () => {
    expect(eventsIn({ ...empty, conflicts: [{ ...meeting, kind: "overtaking" }] }).has("conflict")).toBe(false);
    expect(eventsIn({ ...empty, disruptions: [{ ...fog, kind: "signal_failure" }] }).has("fog")).toBe(false);
  });

  it("is finished only when every train is finished", () => {
    const done = { ...empty, trains: empty.trains.map((t) => ({ ...t, status: "finished" as const })) };
    expect(eventsIn(done).has("finished")).toBe(true);
    expect(eventsIn({ ...done, trains: [...done.trains, { ...done.trains[0], status: "running" as const }] }).has("finished")).toBe(false);
  });
});

describe("advanceDemo", () => {
  it("ignores snapshots while the demo is off", () => {
    expect(advanceDemo(DEMO_IDLE, { ...empty, disruptions: [fog] })).toBe(DEMO_IDLE);
  });

  it("moves the caption to each new event, once", () => {
    let s = advanceDemo(active, { ...empty, disruptions: [fog] });
    expect(s.current).toBe("fog");
    s = advanceDemo(s, { ...empty, disruptions: [fog], conflicts: [meeting] });
    expect(s.current).toBe("conflict");
    s = advanceDemo(s, { ...empty, disruptions: [fog], conflicts: [meeting] });
    expect(s.seen).toEqual(["fog", "conflict"]);
  });

  it("does not go back to an old caption when the fog is still on", () => {
    let s = advanceDemo(active, { ...empty, disruptions: [fog], conflicts: [meeting] });
    expect(s.current).toBe("conflict");
    s = advanceDemo(s, { ...empty, disruptions: [fog] });
    expect(s.current).toBe("conflict");
  });

  it("shows the latest of several events that arrive together", () => {
    const s = advanceDemo(active, { ...empty, disruptions: [fog], conflicts: [meeting], recommendations: [{ ...recommendation, status: "proposed" }] });
    expect(s.current).toBe("recommendation");
    expect(s.seen).toEqual(["fog", "conflict", "recommendation"]);
  });
});

describe("recommendation that vanishes", () => {
  it("only a proposed recommendation counts as one the controller can still apply", () => {
    expect(hasProposal({ ...empty, recommendations: [{ ...recommendation, status: "proposed" }] })).toBe(true);
    expect(hasProposal({ ...empty, recommendations: [{ ...recommendation, status: "ignored" }] })).toBe(false);
    expect(hasProposal(empty)).toBe(false);
  });

  it("rearm lets the recommendation caption come back, and steps the caption back to the previous event", () => {
    let s = advanceDemo(active, { ...empty, disruptions: [fog], conflicts: [meeting], recommendations: [{ ...recommendation, status: "proposed" }] });
    expect(s.current).toBe("recommendation");
    s = rearm(s, "recommendation");
    expect(s.seen).toEqual(["fog", "conflict"]);
    expect(s.current).toBe("conflict");
    s = advanceDemo(s, { ...empty, disruptions: [fog], conflicts: [meeting], recommendations: [{ ...recommendation, status: "proposed" }] });
    expect(s.current).toBe("recommendation");
  });

  it("slows down after the first conflict, within the allowed speed range", () => {
    expect(DEMO_SLOW_SPEED).toBeLessThan(DEMO_SCENARIO.speed);
    expect(DEMO_SLOW_SPEED).toBeGreaterThanOrEqual(0.5);
  });
});
