import { describe, expect, it, vi } from "vitest";

import { buildCommands, filterCommands, type CommandActions, type CommandContext } from "./commands";

function spies(): CommandActions {
  return {
    start: vi.fn(),
    pause: vi.fn(),
    reset: vi.fn(),
    setStrategy: vi.fn(),
    inject: vi.fn(),
    setTab: vi.fn(),
    replay: vi.fn(),
    demo: vi.fn(),
    openHelp: vi.fn(),
    toggleAlerts: vi.fn(),
    toggleTrain: vi.fn(),
  };
}

function context(over: Partial<CommandContext> = {}): CommandContext {
  return { live: true, running: false, strategy: "no_control", actions: spies(), ...over };
}

const find = (ctx: CommandContext, id: string) => {
  const cmd = buildCommands(ctx).find((c) => c.id === id);
  if (!cmd) throw new Error(`no command ${id}`);
  return cmd;
};

describe("buildCommands", () => {
  it("offers the main actions", () => {
    const ids = buildCommands(context()).map((c) => c.id);
    for (const id of ["sim.start", "sim.reset", "strategy.cpsat", "replay.priority", "inject.fog", "inject.block_closure", "tab.map", "tab.time_distance", "tab.compare", "demo.start", "help.shortcuts"]) {
      expect(ids).toContain(id);
    }
  });

  it("has unique ids", () => {
    const ids = buildCommands(context()).map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("shows Start when stopped and Pause when running", () => {
    expect(buildCommands(context({ running: false })).some((c) => c.id === "sim.start")).toBe(true);
    expect(buildCommands(context({ running: false })).some((c) => c.id === "sim.pause")).toBe(false);
    expect(buildCommands(context({ running: true })).some((c) => c.id === "sim.pause")).toBe(true);
  });

  it("runs the matching action", () => {
    const ctx = context();
    find(ctx, "sim.start").run();
    find(ctx, "sim.reset").run();
    find(ctx, "strategy.cpsat").run();
    find(ctx, "inject.fog").run();
    find(ctx, "tab.compare").run();
    find(ctx, "replay.priority").run();
    find(ctx, "demo.start").run();
    find(ctx, "help.shortcuts").run();
    const a = ctx.actions;
    expect(a.start).toHaveBeenCalledOnce();
    expect(a.reset).toHaveBeenCalledOnce();
    expect(a.setStrategy).toHaveBeenCalledWith("cpsat");
    expect(a.inject).toHaveBeenCalledWith("fog");
    expect(a.setTab).toHaveBeenCalledWith("compare");
    expect(a.replay).toHaveBeenCalledWith("priority");
    expect(a.demo).toHaveBeenCalledOnce();
    expect(a.openHelp).toHaveBeenCalledOnce();
  });

  it("disables simulation commands while the backend is offline, but not the tabs or help", () => {
    const ctx = context({ live: false });
    expect(find(ctx, "sim.start").enabled).toBe(false);
    expect(find(ctx, "inject.fog").enabled).toBe(false);
    expect(find(ctx, "demo.start").enabled).toBe(false);
    expect(find(ctx, "tab.time_distance").enabled).toBe(true);
    expect(find(ctx, "help.shortcuts").enabled).toBe(true);
  });

  it("does not offer to switch to the strategy that is already active", () => {
    const ctx = context({ strategy: "priority" });
    expect(find(ctx, "strategy.priority").enabled).toBe(false);
    expect(find(ctx, "strategy.cpsat").enabled).toBe(true);
    expect(find(ctx, "replay.priority").enabled).toBe(false);
  });

  it("shows the keyboard shortcut where one exists", () => {
    expect(find(context(), "tab.time_distance").shortcut).toBe("2");
    expect(find(context(), "sim.start").shortcut).toBe("Space");
  });
});

describe("filterCommands", () => {
  const all = buildCommands(context());

  it("returns everything for an empty query", () => {
    expect(filterCommands(all, "  ")).toHaveLength(all.length);
  });

  it("finds by title words in any order", () => {
    const hits = filterCommands(all, "fog inject").map((c) => c.id);
    expect(hits).toEqual(["inject.fog"]);
  });

  it("finds by keyword", () => {
    expect(filterCommands(all, "string graph").map((c) => c.id)).toEqual(["tab.time_distance"]);
    expect(filterCommands(all, "rewind").map((c) => c.id)).toContain("sim.reset");
  });

  it("ranks title matches first and puts disabled commands last", () => {
    const ctx = context({ strategy: "cpsat" });
    const hits = filterCommands(buildCommands(ctx), "strategy");
    expect(hits[0].enabled).toBe(true);
    expect(hits.at(-1)?.enabled).toBe(false);
    expect(hits.filter((c) => !c.enabled).map((c) => c.id)).toContain("strategy.cpsat");
  });

  it("returns nothing when nothing matches", () => {
    expect(filterCommands(all, "zzzzqq")).toEqual([]);
  });
});
