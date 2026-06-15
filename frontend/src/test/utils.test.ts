/**
 * Tests for @/lib/utils
 *
 * Covers: cn, formatPercent, formatCurrency, formatNumber, truncate
 */

import { describe, it, expect } from "vitest";
import { cn, formatPercent, formatCurrency, formatNumber, truncate } from "@/lib/utils";

// ── cn ────────────────────────────────────────────────────────────────────────

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("handles conditional classes (falsy values ignored)", () => {
    // eslint-disable-next-line no-constant-binary-expression
    expect(cn("base", false && "hidden", undefined, null, "active")).toBe(
      "base active",
    );
  });

  it("resolves Tailwind conflicts (last wins)", () => {
    // tailwind-merge: p-4 overrides p-2
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("returns empty string when no classes provided", () => {
    expect(cn()).toBe("");
  });

  it("handles array inputs", () => {
    expect(cn(["foo", "bar"])).toBe("foo bar");
  });
});

// ── formatPercent ─────────────────────────────────────────────────────────────

describe("formatPercent", () => {
  it("formats 0.1234 as 12.34%", () => {
    expect(formatPercent(0.1234)).toBe("12.34%");
  });

  it("formats 0 as 0.00%", () => {
    expect(formatPercent(0)).toBe("0.00%");
  });

  it("formats 1 as 100.00%", () => {
    expect(formatPercent(1)).toBe("100.00%");
  });

  it("respects custom decimal places", () => {
    expect(formatPercent(0.1234, 0)).toBe("12%");
    expect(formatPercent(0.1234, 4)).toBe("12.3400%");
  });

  it("handles negative values", () => {
    expect(formatPercent(-0.05)).toBe("-5.00%");
  });
});

// ── formatCurrency ────────────────────────────────────────────────────────────

describe("formatCurrency", () => {
  it("formats a whole number with two decimal places", () => {
    expect(formatCurrency(1000)).toBe("$1,000.00");
  });

  it("formats a large number with commas", () => {
    expect(formatCurrency(1234567.89)).toBe("$1,234,567.89");
  });

  it("formats zero", () => {
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("formats negative values", () => {
    expect(formatCurrency(-500)).toBe("-$500.00");
  });

  it("rounds to 2 decimal places", () => {
    // 1.005 rounds to 1.01 in most JS engines
    expect(formatCurrency(1.005)).toMatch(/^\$1\.0[01]$/);
  });
});

// ── formatNumber ──────────────────────────────────────────────────────────────

describe("formatNumber", () => {
  it("formats with default 4 decimal places", () => {
    expect(formatNumber(1.23456)).toBe("1.2346");
  });

  it("formats with custom decimal places", () => {
    expect(formatNumber(1.23456, 2)).toBe("1.23");
    expect(formatNumber(1.23456, 0)).toBe("1");
  });

  it("pads with zeros when needed", () => {
    expect(formatNumber(1, 4)).toBe("1.0000");
  });

  it("handles zero", () => {
    expect(formatNumber(0, 2)).toBe("0.00");
  });

  it("handles negative values", () => {
    expect(formatNumber(-3.14159, 3)).toBe("-3.142");
  });
});

// ── truncate ──────────────────────────────────────────────────────────────────

describe("truncate", () => {
  it("returns the string unchanged when it fits within maxLength", () => {
    expect(truncate("hello", 10)).toBe("hello");
  });

  it("returns the string unchanged when exactly at maxLength", () => {
    expect(truncate("hello", 5)).toBe("hello");
  });

  it("truncates and appends ellipsis when string exceeds maxLength", () => {
    expect(truncate("hello world", 8)).toBe("hello w…");
  });

  it("handles empty string", () => {
    expect(truncate("", 5)).toBe("");
  });

  it("handles maxLength of 1", () => {
    // slice(0, 0) + "…" = "…"
    expect(truncate("abc", 1)).toBe("…");
  });
});
