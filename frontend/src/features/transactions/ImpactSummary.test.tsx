import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MetricChange, SpendingInsight } from "@/api/types";
import { asMoney, asRate } from "@/lib/money";
import { ImpactSummary } from "@/features/transactions/ImpactSummary";

function change(
  name: string,
  unit: MetricChange["unit"],
  before: string,
  after: string,
  delta: string,
): MetricChange {
  return { name, unit, before, after, delta, is_material: delta !== "0.00" && delta !== "0.000000" };
}

/** The demo household taking on R14,500 of rent — the same reference case the backend's
 * tests/domain/test_spending_impact.py works from, so the two ends agree on the figures. */
function insight(overrides: Partial<SpendingInsight> = {}): SpendingInsight {
  return {
    months_covered: 1,
    period_start: "2026-09-01",
    period_end: "2026-09-30",
    rows_needing_review: 0,
    rows: [],
    by_purpose: [
      {
        key: "rent",
        label: "Rent",
        total: asMoney("14500.00"),
        monthly_average: asMoney("14500.00"),
        count: 1,
      },
    ],
    by_method: [],
    commitments: [
      {
        label: "rent property group",
        merchant: "rent property group",
        method: "debit_order",
        purpose: "rent",
        monthly_amount: asMoney("14500.00"),
        occurrences: 1,
        is_new: true,
      },
    ],
    impact: {
      before: {
        income: asMoney("52000.00"),
        essential: asMoney("16900.00"),
        discretionary: asMoney("9800.00"),
        saving: asMoney("0.00"),
        debt_service: asMoney("0.00"),
      },
      after: {
        income: asMoney("52000.00"),
        essential: asMoney("31400.00"),
        discretionary: asMoney("9800.00"),
        saving: asMoney("0.00"),
        debt_service: asMoney("0.00"),
      },
      added: {
        income: asMoney("0.00"),
        essential: asMoney("14500.00"),
        discretionary: asMoney("0.00"),
        saving: asMoney("0.00"),
        debt_service: asMoney("0.00"),
      },
      changes: [
        change("monthly_income", "money", "52000.00", "52000.00", "0.00"),
        change("monthly_essential", "money", "16900.00", "31400.00", "14500.00"),
        change("monthly_cash_flow", "money", "25300.00", "10800.00", "-14500.00"),
        change("cash_flow_margin", "rate", "0.486538", "0.207692", "-0.278846"),
        change("emergency_fund_months", "months", "2.852071", "1.535032", "-1.317039"),
      ],
    },
    affected: [
      {
        area: "forecast",
        effect: "will be marked stale",
        detail: "Every projection rests on the baselines these transactions change.",
      },
    ],
    ...overrides,
  };
}

describe("ImpactSummary", () => {
  it("shows each moved figure before and after", () => {
    render(<ImpactSummary insight={insight()} heading="What this file would change" />);

    expect(screen.getByRole("rowheader", { name: "Essential spending" })).toBeVisible();
    expect(screen.getByText(/R\s?16[\s,]?900/)).toBeInTheDocument();
    expect(screen.getByText(/R\s?31[\s,]?400/)).toBeInTheDocument();
  });

  it("renders each figure in the unit the server declared", () => {
    // The unit travels with the change precisely so nothing here has to infer from a name
    // whether 0.207692 is twenty cents or twenty percent.
    render(<ImpactSummary insight={insight()} heading="Impact" />);

    expect(screen.getByText("20.8%")).toBeInTheDocument();
    expect(screen.getByText(/1\.5 months/)).toBeInTheDocument();
  });

  it("leaves out figures the import does not move", () => {
    render(<ImpactSummary insight={insight()} heading="Impact" />);

    expect(screen.queryByRole("rowheader", { name: "Monthly income" })).not.toBeInTheDocument();
  });

  it("says the figures are monthly averages over the period", () => {
    // A six-month statement adds six months of rent. Without this line a reader has no way
    // to know whether "after" is a month or the whole file.
    render(<ImpactSummary insight={insight({ months_covered: 6 })} heading="Impact" />);

    expect(screen.getByText(/monthly averages over the period covered/)).toBeVisible();
    expect(screen.getByText(/6 months/)).toBeVisible();
  });

  it("names a new standing commitment with its type and purpose", () => {
    render(<ImpactSummary insight={insight()} heading="Impact" />);

    expect(screen.getByText("rent property group")).toBeVisible();
    expect(screen.getByText("Debit order")).toBeVisible();
    expect(screen.getAllByText("Rent").length).toBeGreaterThan(0);
  });

  it("does not list a commitment the user already had", () => {
    const existing = insight();
    render(
      <ImpactSummary
        insight={{
          ...existing,
          commitments: [{ ...existing.commitments[0], is_new: false }],
        }}
        heading="Impact"
      />,
    );

    expect(screen.queryByText("New standing commitments")).not.toBeInTheDocument();
  });

  it("flags rows that were not recognised", () => {
    render(<ImpactSummary insight={insight({ rows_needing_review: 3 })} heading="Impact" />);

    expect(screen.getByText(/3\s+payments were not\s+recognised/)).toBeVisible();
  });

  it("says plainly when nothing moved", () => {
    const flat = insight();
    render(
      <ImpactSummary
        insight={{
          ...flat,
          impact: {
            ...flat.impact,
            changes: [change("monthly_essential", "money", "16900.00", "16900.00", "0.00")],
          },
        }}
        heading="Impact"
      />,
    );

    expect(screen.getByText("Nothing in this file moves a monthly figure.")).toBeVisible();
  });

  it("lists what else the import changes", () => {
    render(<ImpactSummary insight={insight()} heading="Impact" />);

    expect(screen.getByText("What else this changes")).toBeVisible();
    expect(screen.getByText(/Every projection rests on the baselines/)).toBeInTheDocument();
  });

  it("renders a rate of zero without claiming a direction", () => {
    const flat = insight();
    render(
      <ImpactSummary
        insight={{
          ...flat,
          impact: {
            ...flat.impact,
            changes: [
              {
                ...change("cash_flow_margin", "rate", "0.400000", "0.400000", "0.000000"),
                is_material: true,
              },
            ],
          },
        }}
        heading="Impact"
      />,
    );

    // "0.000000" is not "0", which is why the zero test narrows rather than comparing
    // strings — see isZeroFigure in src/lib/money.ts.
    expect(screen.getByLabelText("unchanged")).toBeInTheDocument();
  });

  it("accepts a rate typed as Rate and money typed as Money", () => {
    // A compile-time assertion as much as a runtime one: the branded types are what stop a
    // Money value being handed to a percentage formatter.
    expect(asRate("0.207692")).toBe("0.207692");
    expect(asMoney("10800.00")).toBe("10800.00");
  });
});
