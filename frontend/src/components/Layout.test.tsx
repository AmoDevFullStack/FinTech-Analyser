import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { Layout } from "@/components/Layout";

vi.mock("@/api/auth", () => ({
  useCurrentUser: () => ({ data: { email: "demo@financialdigitaltwin.local" } }),
  useLogout: () => ({ mutate: vi.fn() }),
}));

function renderLayout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<p>Dashboard content</p>} />
            <Route path="/accounts" element={<p>Accounts content</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** ADR-009. Queried by role and accessible name, per docs/frontend.md §8, so the test
 * fails if the drawer stops being operable by assistive technology.
 */
describe("Layout navigation", () => {
  it("keeps destinations out of the accessibility tree until the menu is opened", () => {
    renderLayout();

    expect(screen.queryByRole("link", { name: "Accounts" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("opens the drawer from the menu control", () => {
    renderLayout();

    fireEvent.click(screen.getByRole("button", { name: "Menu" }));

    expect(screen.getByRole("link", { name: "Accounts" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "true");
  });

  it("closes on Escape and returns focus to the menu control", () => {
    renderLayout();
    const menuButton = screen.getByRole("button", { name: "Menu" });

    fireEvent.click(menuButton);
    fireEvent.keyDown(document, { key: "Escape" });

    expect(menuButton).toHaveAttribute("aria-expanded", "false");
    expect(menuButton).toHaveFocus();
  });

  it("closes when a destination is followed", () => {
    renderLayout();

    fireEvent.click(screen.getByRole("button", { name: "Menu" }));
    fireEvent.click(screen.getByRole("link", { name: "Accounts" }));

    expect(screen.getByText("Accounts content")).toBeVisible();
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("keeps Ask out of the destination list and promotes it in the header", () => {
    renderLayout();
    // ADR-009: Ask is a conversation, not a destination.
    expect(screen.getAllByRole("button", { name: "Ask" }).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Menu" }));

    expect(screen.queryByRole("link", { name: "Ask" })).not.toBeInTheDocument();
  });
});
