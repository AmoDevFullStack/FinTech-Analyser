import { LogOut } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { useCurrentUser, useLogout } from "@/api/auth";
import { Button } from "@/components/Button";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard" },
  { to: "/accounts", label: "Accounts" },
  { to: "/transactions", label: "Transactions" },
  { to: "/scenarios", label: "Scenarios" },
];

export function Layout() {
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-6 py-8 font-ui text-content">
      <header className="flex items-center justify-between gap-6 border-b border-rule pb-4">
        <nav className="flex gap-6">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `text-label font-medium ${isActive ? "text-accent" : "text-content-secondary"}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        {user ? (
          <div className="flex items-center gap-4">
            <span className="text-caption text-content-tertiary">{user.email}</span>
            <Button icon={LogOut} onClick={() => logout.mutate()}>
              Log out
            </Button>
          </div>
        ) : null}
      </header>
      <main className="flex flex-1 flex-col gap-8">
        <Outlet />
      </main>
    </div>
  );
}
