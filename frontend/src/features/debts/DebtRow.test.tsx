import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Debt } from "@/api/types";
import { asMoney, asRate } from "@/lib/money";
import { DebtRow } from "@/features/debts/DebtRow";

const updateMutate = vi.fn();
const deleteMutate = vi.fn();

vi.mock("@/api/debts", () => ({
  useUpdateDebt: () => ({ mutate: updateMutate, isPending: false, isError: false, error: null }),
  useDeleteDebt: () => ({ mutate: deleteMutate, isPending: false, isError: false, error: null }),
}));

function debt(overrides: Partial<Debt> = {}): Debt {
  return {
    id: "0192f0c1-0000-7000-8000-000000000001",
    account_id: null,
    debt_type: "credit_card",
    original_principal: asMoney("20000.00"),
    current_balance: asMoney("18400.00"),
    annual_rate: asRate("0.240000"),
    minimum_payment: asMoney("600.00"),
    instalment: null,
    term_months: null,
    started_on: "2026-01-15",
    ...overrides,
  };
}

function renderRow(overrides: Partial<Debt> = {}) {
  return render(
    <MemoryRouter>
      <ul>
        <DebtRow debt={debt(overrides)} />
      </ul>
    </MemoryRouter>,
  );
}

describe("DebtRow", () => {
  beforeEach(() => {
    updateMutate.mockReset();
    deleteMutate.mockReset();
  });

  it("opens the editor when the row is clicked", () => {
    renderRow();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit Credit card", expanded: false }));

    expect(screen.getByRole("button", { name: "Save changes" })).toBeVisible();
  });

  it("makes the row a real button so it is reachable by keyboard", () => {
    // The only way to edit a debt. A clickable div would leave the feature unusable
    // without a mouse and invisible to a screen reader.
    renderRow();
    const row = screen.getByRole("button", { name: "Edit Credit card", expanded: false });

    expect(row.tagName).toBe("BUTTON");
    expect(row).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps the schedule link separate from the editing control", () => {
    // A link nested inside a button is invalid HTML and browsers resolve it by ignoring
    // one of the two, unpredictably. They stay siblings.
    renderRow();
    const link = screen.getByRole("link", { name: "Open the Credit card schedule" });

    expect(link).toHaveAttribute("href", "/debts/0192f0c1-0000-7000-8000-000000000001");
    expect(link.closest("button")).toBeNull();
  });

  it("sends only the fields that changed", () => {
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Credit card", expanded: false }));

    fireEvent.change(screen.getByLabelText("Current balance"), {
      target: { value: "17250.00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(updateMutate).toHaveBeenCalledTimes(1);
    const [payload] = updateMutate.mock.calls[0];
    expect(payload.debtId).toBe("0192f0c1-0000-7000-8000-000000000001");
    expect(payload.data).toEqual({ current_balance: "17250.00" });
  });

  it("passes the balance through as the string the field produced", () => {
    // docs/frontend.md §4: parsing money is the API's job, and src/lib/money.ts is the
    // only place this tree may narrow a money string at all.
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Credit card", expanded: false }));
    fireEvent.change(screen.getByLabelText("Current balance"), {
      target: { value: "17250.55" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(updateMutate.mock.calls[0][0].data.current_balance).toBe("17250.55");
  });

  it("does not call the API when nothing was edited", () => {
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Credit card", expanded: false }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(updateMutate).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });

  it("asks before removing a debt", () => {
    renderRow();

    fireEvent.click(screen.getByRole("button", { name: "Remove Credit card" }));

    expect(deleteMutate).not.toHaveBeenCalled();
    expect(
      screen.getByText(/takes its instalment out of every projection/),
    ).toBeVisible();
  });

  it("removes the debt once the confirmation is taken", () => {
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Remove Credit card" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm removing Credit card" }));

    expect(deleteMutate).toHaveBeenCalledWith("0192f0c1-0000-7000-8000-000000000001");
  });

  it("lets the user back out of removing", () => {
    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Remove Credit card" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel removing" }));

    expect(deleteMutate).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Remove Credit card" })).toBeVisible();
  });

  it("offers a term field for a fixed-term debt and says a blank means revolving otherwise", () => {
    const { unmount } = renderRow({ debt_type: "vehicle", term_months: 72 });
    fireEvent.click(screen.getByRole("button", { name: "Edit Vehicle finance", expanded: false }));
    expect(screen.getByLabelText(/Term in months/)).toHaveValue("72");
    unmount();

    renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Edit Credit card", expanded: false }));
    expect(screen.getByLabelText(/blank for a revolving facility/)).toHaveValue("");
  });
});
