import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useCurrentUser } from "@/api/auth";
import { Layout } from "@/components/Layout";
import { EmptyState } from "@/components/EmptyState";
import { Accounts } from "@/pages/Accounts";
import { Dashboard } from "@/pages/Dashboard";
import { Health } from "@/pages/Health";
import { Login } from "@/pages/Login";
import { Register } from "@/pages/Register";
import { ScenarioDetail } from "@/pages/ScenarioDetail";
import { Scenarios } from "@/pages/Scenarios";
import { Transactions } from "@/pages/Transactions";

function RequireAuth({ children }: { children: ReactNode }) {
  const { data: user, isLoading, isError } = useCurrentUser();

  if (isLoading) return <EmptyState message="Loading…" />;
  if (isError || !user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/health" element={<Health />} />
        <Route path="/accounts" element={<Accounts />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/scenarios" element={<Scenarios />} />
        <Route path="/scenarios/:scenarioId" element={<ScenarioDetail />} />
      </Route>
    </Routes>
  );
}
