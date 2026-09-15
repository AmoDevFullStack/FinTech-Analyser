import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useCurrentUser } from "@/api/auth";
import { Layout } from "@/components/Layout";
import { EmptyState } from "@/components/EmptyState";
import { Accounts } from "@/pages/Accounts";
import { Assistant } from "@/pages/Assistant";
import { Dashboard } from "@/pages/Dashboard";
import { DebtDetail } from "@/pages/DebtDetail";
import { Debts } from "@/pages/Debts";
import { Forecast } from "@/pages/Forecast";
import { Goals } from "@/pages/Goals";
import { Health } from "@/pages/Health";
import { Login } from "@/pages/Login";
import { Recommendations } from "@/pages/Recommendations";
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
        <Route path="/debts" element={<Debts />} />
        <Route path="/debts/:debtId" element={<DebtDetail />} />
        <Route path="/goals" element={<Goals />} />
        <Route path="/forecast" element={<Forecast />} />
        <Route path="/worth-knowing" element={<Recommendations />} />
        <Route path="/ask" element={<Assistant />} />
        <Route path="/scenarios" element={<Scenarios />} />
        <Route path="/scenarios/:scenarioId" element={<ScenarioDetail />} />
      </Route>
    </Routes>
  );
}
