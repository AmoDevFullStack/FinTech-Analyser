import { describe, expect, it } from "vitest";

import { asMoney, asRate, formatMoney, formatRateAsPercent, isNegative } from "@/lib/money";

describe("formatMoney", () => {
  it("formats the dashboard worked example net worth in en-ZA convention", () => {
    // en-ZA groups with a space and uses a comma decimal — the authentic South African
    // convention, not the US-style comma-thousands/dot-decimal this test used to assume.
    expect(formatMoney(asMoney("412500.00"))).toMatch(/^R\s*412\s*500,00$/);
  });

  it("formats a negative value with its sign", () => {
    expect(isNegative(asMoney("-300.00"))).toBe(true);
    expect(isNegative(asMoney("300.00"))).toBe(false);
  });
});

describe("formatRateAsPercent", () => {
  it("matches the scenario worked example debt-to-income ratio", () => {
    expect(formatRateAsPercent(asRate("0.283931"))).toBe("28.4%");
  });
});
