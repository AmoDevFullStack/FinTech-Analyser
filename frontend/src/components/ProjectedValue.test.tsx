import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectedValue } from "@/components/ProjectedValue";
import { asMoney } from "@/lib/money";

describe("ProjectedValue", () => {
  it("renders the value together with its generation date — never the value alone", () => {
    render(
      <ProjectedValue
        projected={{ value: asMoney("10800.00"), generatedAt: "2026-09-14T06:00:00+02:00", isStale: false }}
      />,
    );
    expect(screen.getByText(/R\s*10\s*800,00/)).toBeInTheDocument();
    expect(screen.getByText(/Projected/)).toBeInTheDocument();
  });

  it("labels a stale projection as stale", () => {
    render(
      <ProjectedValue
        projected={{ value: asMoney("10800.00"), generatedAt: "2026-09-06T06:00:00+02:00", isStale: true }}
      />,
    );
    expect(screen.getByText(/Stale/)).toBeInTheDocument();
  });
});
