import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { StrategyComparison, StrategyResult } from "@/api/types";
import { asMoney } from "@/lib/money";
import { StrategyComparisonView } from "@/features/debts/StrategyComparisonView";

function result(strategy: string, interest: string, months: number): StrategyResult {
  return {
    strategy,
    months_to_free: months,
    total_interest: asMoney(interest),
    payoff_month_by_debt_id: {},
    schedule: [],
  };
}

function comparison(overrides: Partial<StrategyComparison> = {}): StrategyComparison {
  return {
    avalanche: result("avalanche", "42000.00", 48),
    snowball: result("snowball", "45500.00", 50),
    consolidation: null,
    interest_difference_avalanche_vs_snowball: asMoney("3500.00"),
    months_difference_avalanche_vs_snowball: 2,
    difference_is_material: true,
    ...overrides,
  };
}

describe("StrategyComparisonView", () => {
  it("states the difference in rand and in months", () => {
    render(<StrategyComparisonView comparison={comparison()} />);

    // specs/debts.md: the comparison must quantify the gap both ways — in rand and in
    // months — so both must appear in the sentence that states the difference.
    expect(screen.getByText(/R\s?3[\s,]?500/)).toBeInTheDocument();
    expect(
      screen.getByText((_, element) =>
        Boolean(
          element?.tagName === "P" &&
            /Snowball costs/.test(element.textContent ?? "") &&
            /2\s*months longer/.test(element.textContent ?? ""),
        ),
      ),
    ).toBeInTheDocument();
  });

  it("says so plainly when the difference is not material", () => {
    render(
      <StrategyComparisonView
        comparison={comparison({
          difference_is_material: false,
          interest_difference_avalanche_vs_snowball: asMoney("120.00"),
          months_difference_avalanche_vs_snowball: 0,
        })}
      />,
    );

    expect(screen.getByText("Difference is not material")).toBeInTheDocument();
    expect(
      screen.getByText(/adherence matters more than the ranking/),
    ).toBeInTheDocument();
  });

  it("does not mark either strategy as the recommended one", () => {
    render(<StrategyComparisonView comparison={comparison()} />);

    // The spec is explicit: the system presents costs and lets the user choose. Any
    // wording that picks for them is a regression against that.
    expect(screen.queryByText(/recommended/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/you should/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/best/i)).not.toBeInTheDocument();
  });

  it("shows consolidation only when the server returned one", () => {
    const { rerender } = render(<StrategyComparisonView comparison={comparison()} />);
    expect(screen.queryByText(/Consolidation/)).not.toBeInTheDocument();

    rerender(
      <StrategyComparisonView
        comparison={comparison({ consolidation: result("consolidation", "51000.00", 54) })}
      />,
    );
    expect(screen.getByText(/Consolidation/)).toBeInTheDocument();
  });
});
