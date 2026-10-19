import { LogOut, Menu, MessageSquareText, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useCurrentUser, useLogout } from "@/api/auth";
import { Button } from "@/components/Button";

/** Nine destinations in a row was a tab bar pretending to be navigation: it wrapped to two
 * lines under 900px, gave every destination equal weight, and left nowhere to put the
 * tenth. They now live behind one menu control, which also gives back the whole header
 * width for the product name and the one action worth promoting.
 *
 * "Ask" is deliberately NOT in this list — it is a conversation, not a page, and it opens
 * as its own full-height surface. See docs/frontend.md §7 and ADR-009.
 */
const NAV_ITEMS = [
  { to: "/", label: "Dashboard" },
  { to: "/health", label: "Health" },
  { to: "/accounts", label: "Accounts" },
  { to: "/transactions", label: "Transactions" },
  { to: "/debts", label: "Debts" },
  { to: "/goals", label: "Goals" },
  { to: "/forecast", label: "Forecast" },
  { to: "/scenarios", label: "Scenarios" },
  { to: "/worth-knowing", label: "Worth knowing" },
];

export function Layout() {
  const { data: user } = useCurrentUser();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // A destination change closes the menu, so following a link never leaves the drawer
  // covering the page it just navigated to.
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  // Escape closes, and focus returns to the control that opened it — without this the
  // keyboard user is left tabbing from the start of the document (design-system.md §11).
  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    panelRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  return (
    <div className="flex min-h-screen flex-col font-ui text-content">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-surface-raised focus:px-4 focus:py-2 focus:text-label focus:shadow-2"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-30 border-b border-rule bg-glass shadow-1 backdrop-blur-xl backdrop-saturate-150 [@media(prefers-reduced-transparency:reduce)]:bg-surface-raised [@media(prefers-reduced-transparency:reduce)]:backdrop-blur-none">
        <div className="mx-auto flex h-16 w-full max-w-[1200px] items-center gap-3 px-4 sm:px-6">
          <button
            ref={menuButtonRef}
            type="button"
            aria-label="Menu"
            aria-expanded={menuOpen}
            aria-controls="primary-navigation"
            onClick={() => setMenuOpen((open) => !open)}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-rule bg-surface-raised text-content transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
          >
            <Menu size={20} strokeWidth={2} aria-hidden="true" />
          </button>

          <h1 className="text-title tracking-tight">Financial Digital Twin</h1>

        </div>
      </header>

      {menuOpen ? (
        <div
          className="fixed inset-0 z-40 bg-scrim transition-opacity duration-150"
          onClick={() => setMenuOpen(false)}
          aria-hidden="true"
        />
      ) : null}

      {menuOpen ? (
        <div
          ref={panelRef}
          id="primary-navigation"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
          className="fixed inset-y-0 left-0 z-50 flex w-[min(20rem,85vw)] animate-drawer-in flex-col gap-2 border-r border-rule bg-surface-raised p-4 shadow-3"
        >
          <div className="flex items-center justify-between pb-2">
            <span className="text-label text-content-secondary">Menu</span>
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => {
                setMenuOpen(false);
                menuButtonRef.current?.focus();
              }}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full text-content-secondary transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <X size={20} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>

          <nav className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `flex min-h-[44px] items-center rounded-lg px-3 text-body transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                    isActive
                      ? "bg-surface-sunken font-medium text-accent"
                      : "text-content-secondary hover:bg-surface-sunken hover:text-content"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          {user ? (
            <div className="mt-auto flex flex-col gap-3 border-t border-rule pt-4">
              <span className="text-caption text-content-tertiary">
                {user.email}
              </span>
              <Button icon={LogOut} onClick={() => logout.mutate()}>
                Log out
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      <main
        id="main"
        className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col gap-8 px-4 pb-28 pt-8 sm:px-6"
      >
        <Outlet />
      </main>

      {/* Ask sits at the bottom, within thumb reach, rather than in the header beside the
          menu. It is the one control a reader reaches for in the middle of reading
          something — having read a figure they do not understand — so it belongs where the
          hand already is, not at the far end of the screen from it.

          `pb-28` on <main> reserves the space so the button never covers the last row of a
          page, and the safe-area inset keeps it clear of a phone's home indicator. */}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-end px-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-6">
        <Button
          variant="primary"
          icon={MessageSquareText}
          onClick={() => navigate("/ask")}
          className="pointer-events-auto shadow-2"
        >
          Ask
        </Button>
      </div>
    </div>
  );
}
