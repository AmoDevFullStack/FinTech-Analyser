import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MonthReport, Position } from "@/api/types";
import { CashFlowRegion } from "@/features/dashboard/CashFlowRegion";
import { asMoney, asRate } from "@/lib/money";

const useMonthlySummaryMock = vi.fn();

vi.mock("@/api/transactions", () => ({
  useMonthlySummary: () => useMonthlySummaryMock(),
}));

function position(overrides: Partial<Position> = {}): Position {
  return {
    as_of: "2026-07-31T06:00:00+02:00",
    net_worth: asMoney("48200.00"),
    liquid_savings: asMoney("48200.00"),
    total_debt: asMoney("0.00"),
    monthly_income: asMoney("0.00"),
    monthly_essential: asMoney("0.00"),
    monthly_discretionary: asMoney("0.00"),
    projected_cash_flow: asMoney("0.00"),
    emergency_fund_months: "0.90",
    baseline_month: "2026-07",
    months_of_history: 3,
    transactions_counted: 84,
    last_transaction_on: "2026-07-24",
    health_score: 61,
    health_generated_at: "2026-07-31T06:00:00+02:00",
    health_score_change: 2,
    health_largest_negative_contributor: "debt_load",
    upcoming_obligations: [],
    active_risk_flags: 0,
    is_stale: false,
    ...overrides,
  };
}

function month(): MonthReport {
  return {
    month: "2026-07",
    previous_month: "2026-06",
    totals: {
      income: asMoney("52000.00"),
      essential: asMoney("31400.00"),
      discretionary: asMoney("9800.00"),
      saving: asMoney("3000.00"),
      debt_service: asMoney("0.00"),
      spending: asMoney("44200.00"),
      net: asMoney("7800.00"),
    },
    changes: {
      income: {
        previous: asMoney("52000.00"),
        current: asMoney("52000.00"),
        change: asMoney("0.00"),
        percentage_change: asRate("0.000000"),
      },
      essential: {
        previous: asMoney("16900.00"),
        current: asMoney("31400.00"),
        change: asMoney("14500.00"),
        percentage_change: asRate("0.857988"),
      },
      net: {
        previous: asMoney("22300.00"),
        current: asMoney("7800.00"),
        change: asMoney("-14500.00"),
        percentage_change: asRate("-0.650224"),
      },
    },
    cash: {
      opening: asMoney("37400.00"),
      inflow: asMoney("52000.00"),
      outflow: asMoney("41200.00"),
      closing: asMoney("48200.00"),
    },
    transaction_count: 84,
    import_batch_ids: [],
  };
}

describe("CashFlowRegion", () => {
  beforeEach(() => {
    useMonthlySummaryMock.mockReset().mockReturnValue({ data: undefined });
  });

  it("shows the month's own totals, not the snapshot averages", () => {
    useMonthlySummaryMock.mockReturnValue({ data: { data: [month()], months: 1 } });
    render(<CashFlowRegion position={position()} />);

    // The snapshot says 0,00 for all four. The month says what actually happened.
    expect(screen.getByText("R 52 000,00")).toBeVisible();
    expect(screen.getByText("R 31 400,00")).toBeVisible();
  });

  it("shows how each figure moved since last month", () => {
    useMonthlySummaryMock.mockReturnValue({ data: { data: [month()], months: 1 } });
    render(<CashFlowRegion position={position()} />);

    expect(screen.getByText(/against June 2026/)).toBeVisible();
    expect(screen.getByText("Same as last month")).toBeVisible();
    expect(screen.getByText("-R 14 500,00")).toBeVisible();
  });

  it("falls back to the stored position when there are no months yet", () => {
    useMonthlySummaryMock.mockReturnValue({ data: { data: [], months: 0 } });
    render(<CashFlowRegion position={position({ monthly_income: asMoney("52000.00") })} />);

    expect(screen.getByText("R 52 000,00")).toBeVisible();
    expect(screen.queryByText(/against/)).not.toBeInTheDocument();
  });

  it("shows the last month with activity rather than an empty current month", () => {
    // A user whose statements end in July, looking at the dashboard in September.
    const july = month();
    const september: MonthReport = {
      ...month(),
      month: "2026-09",
      previous_month: "2026-08",
      totals: {
        income: asMoney("0.00"),
        essential: asMoney("0.00"),
        discretionary: asMoney("0.00"),
        saving: asMoney("0.00"),
        debt_service: asMoney("0.00"),
        spending: asMoney("0.00"),
        net: asMoney("0.00"),
      },
      changes: {},
      transaction_count: 0,
    };
    useMonthlySummaryMock.mockReturnValue({ data: { data: [july, september], months: 2 } });
    render(<CashFlowRegion position={position()} />);

    expect(screen.getByText(/most recent month with activity/)).toBeVisible();
    expect(screen.getByText("R 52 000,00")).toBeVisible();
  });

  it("says there is no history when the snapshot has none", () => {
    render(<CashFlowRegion position={position({ monthly_income: null })} />);

    expect(screen.getByText("No transaction history yet.")).toBeVisible();
  });
});
