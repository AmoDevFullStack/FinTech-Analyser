import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreGauge, scoreBand } from "@/components/ScoreGauge";

describe("scoreBand", () => {
  it("bands a score into poor, fair, or good", () => {
    expect(scoreBand(0)).toBe("poor");
    expect(scoreBand(39)).toBe("poor");
    expect(scoreBand(40)).toBe("fair");
    expect(scoreBand(69)).toBe("fair");
    expect(scoreBand(70)).toBe("good");
    expect(scoreBand(100)).toBe("good");
  });
});

describe("ScoreGauge", () => {
  it("names the score and its band in an accessible label, not colour alone", () => {
    render(<ScoreGauge value={72} label="Financial health score" />);

    expect(
      screen.getByRole("img", { name: "Financial health score: 72 of 100, Strong" }),
    ).toBeVisible();
  });

  it("still shows the number and band name as text at every band", () => {
    const { rerender } = render(<ScoreGauge value={20} label="Score" />);
    expect(screen.getByText("20")).toBeVisible();
    expect(screen.getByText("Needs attention")).toBeVisible();

    rerender(<ScoreGauge value={55} label="Score" />);
    expect(screen.getByText("55")).toBeVisible();
    expect(screen.getByText("Fair")).toBeVisible();
  });

  it("drops the band label in compact sizing but keeps the number", () => {
    render(<ScoreGauge value={82} size={56} label="Score" />);
    expect(screen.getByText("82")).toBeVisible();
    expect(screen.queryByText("Strong")).not.toBeInTheDocument();
  });
});
