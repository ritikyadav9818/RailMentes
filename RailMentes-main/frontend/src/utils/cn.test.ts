import { describe, expect, it } from "vitest";

import { cn } from "./cn";

describe("cn", () => {
  it("keeps a custom font size next to a text colour", () => {
    expect(cn("text-body text-text")).toBe("text-body text-text");
    expect(cn("text-caption text-muted", "text-micro")).toBe("text-muted text-micro");
  });

  it("still resolves real conflicts", () => {
    expect(cn("text-text", "text-muted")).toBe("text-muted");
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-sm", "text-body")).toBe("text-body");
  });
});
