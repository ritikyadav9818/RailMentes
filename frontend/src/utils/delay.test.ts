import { describe, expect, it } from "vitest";

import { DELAY_COLORS, delayColor, delayLevel, formatDelay } from "./delay";

describe("delayLevel", () => {
  it("puts the boundaries in the lower bucket (5 / 15 / 30 minutes)", () => {
    expect(delayLevel(0)).toBe("on_time");
    expect(delayLevel(5)).toBe("on_time");
    expect(delayLevel(5.1)).toBe("minor");
    expect(delayLevel(15)).toBe("minor");
    expect(delayLevel(16)).toBe("major");
    expect(delayLevel(30)).toBe("major");
    expect(delayLevel(31)).toBe("severe");
    expect(delayLevel(240)).toBe("severe");
  });

  it("counts early trains as on time", () => {
    expect(delayLevel(-12)).toBe("on_time");
  });

  it("gives every level its own colour", () => {
    expect(new Set(Object.values(DELAY_COLORS)).size).toBe(4);
    expect(delayColor(3)).toBe(DELAY_COLORS.on_time);
    expect(delayColor(40)).toBe(DELAY_COLORS.severe);
  });
});

describe("formatDelay", () => {
  it("reads naturally", () => {
    expect(formatDelay(0)).toBe("on time");
    expect(formatDelay(12)).toBe("+12 min");
    expect(formatDelay(-3)).toBe("3 min early");
    expect(formatDelay(11.6)).toBe("+12 min");
  });
});
