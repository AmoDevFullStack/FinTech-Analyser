import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MonthReport } from "@/api/types";
import { MonthComparison } from "@/features/transactions/MonthComparison";
import { asMoney, asRate } from "@/lib/money";

const useMonthlySummaryMock = vi.fn();

vi.mock("@/api/transactions", () => ({
  useMonthlySummary: () => useMonthlySummaryMock(),
}));

function month(overrides: Partial<MonthReport> = {}): MonthReport {
  return {
    month: "2026-07",
    previous_month: "2026-06",
    totals: {
      income: asMoney("52000.00"),
      essential: asMoney("31400.00"),
      discretionary: asMoney("9800.00"),
      saving: asMoney("0.00"),
      debt_service: asMoney("0.00"),
      spending: asMoney("41200.00"),
      net: asMoney("10800.00"),
    },
    changes: {
      essential: {
        previous: asMoney("16900.00"),
        current: asMoney("31400.00"),
        change: asMoney("14500.00"),
        percentage_change: asRate("0.857988"),
      },
      saving: {
        previous: asMoney("0.00"),
        current: asMoney("3000.00"),
        change: asMoney("3000.00"),
        percentage_change: null,
      },
    },
    cash: {
      opening: asMoney("37400.00"),
      inflow: asMoney("52000.00"),
      outflow: asMoney("41200.00"),
      closing: asMoney("48200.00"),
    },
    transaction_count: 84,
    import_batch_ids: ["0198e1c2-0000-7000-8000-000000000001"],
    ...overrides,
  };
}

describe("MonthComparison", () => {
  beforeEach(() => {
    useMonthlySummaryMock.mockReset();
  });

  it("opens on the most recent month", () => {
    useMonthlySummaryMock.mockReturnValue({
      data: { data: [month({ month: "2026-06", previous_month: "2026-05" }), month()], months: 2 },
      isLoading: false,
      isError: false,
    });
    render(<MonthComparison />);

    expect(screen.getByText("Left over in July 2026")).toBeVisible();
    expect(screen.getByRole("combobox")).toHaveValue("2026-07");
  });

  it("shows a month against the one before it", () => {
    useMonthlySummaryMock.mockReturnValue({
      data: { data: [month()], months: 1 },
      isLoading: false,
      isError: false,
    });
    render(<MonthComparison />);

    expect(screen.getByRole("columnheader", { name: "June 2026" })).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "July 2026" })).toBeVisible();
    expect(screen.getByRole("rowheader", { name: "Essentials" })).toBeVisible();
    expect(screen.getByText("85.8%")).toBeVisible();
  });

  it("shows no percentage where last month was zero", () => {
    useMonthlySummaryMock.mockReturnValue({
      data: { data: [month()], months: 1 },
      isLoading: false,
      isError: false,
    });
    render(<MonthComparison />);

    // The "Put away" row went 0 -> 3,000. The amount is shown; a percentage is not,
    // because there is none to show.
    const row = screen.getByRole("rowheader", { name: "Put away" }).closest("tr");
    expect(row).not.toBeNull();
    // Intl separates thousands with a non-breaking space, so normalise before comparing.
    const text = (row?.textContent ?? "").replace(/\u00a0/g, " ");
    expect(text).toContain("3 000,00");
    expect(text).not.toMatch(/%/);
  });

  it("shows the account balance at each end of the month", () => {
    useMonthlySummaryMock.mockReturnValue({
      data: { data: [month()], months: 1 },
      isLoading: false,
      isError: false,
    });
    render(<MonthComparison />);

    expect(screen.getByText("In the account at month end")).toBeVisible();
    expect(screen.getByText(/Started the month with/)).toBeVisible();
  });

  it("says nothing about cash when there is no balance to show", () => {
    useMonthlySummaryMock.mockReturnValue({
      data: { data: [month({ cash: null })], months: 1 },
      isLoading: false,
      isError: false,
    });
    render(<MonthComparison />);

    expect(screen.queryByText("In the account at month end")).not.toBeInTheDocument();
    expect(screen.getByText("Left over in July 2026")).toBeVisible();
  });

  it("switches month when another is picked", () => {
    useMonthlySummaryMock.mockReturnValue({
      data: {
        data: [month({ month: "2026-06", previous_month: "2026-05" }), month()],
        months: 2,
      },
      isLoading: false,
      isError: false,
    });
    render(<MonthComparison />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "2026-06" } });

    expect(screen.getByText("Left over in June 2026")).toBeVisible();
  });

  it("says where the figures came from", () => {
    useMonthlySummaryMock.mockReturnValue({
      data: { data: [month()], months: 1 },
      isLoading: false,
      isError: false,
    });
    render(<MonthComparison />);

    expect(screen.getByText(/84 transactions/)).toBeVisible();
    expect(screen.getByText(/1 statement you uploaded/)).toBeVisible();
  });

  it("invites an upload when there is nothing yet", () => {
    useMonthlySummaryMock.mockReturnValue({
      data: { data: [], months: 0 },
      isLoading: false,
      isError: false,
    });
    render(<MonthComparison />);

    expect(screen.getByText(/Upload a statement/)).toBeVisible();
  });
});
