import { useDebts, useDebtStrategies } from "@/api/debts";
import { EmptyState } from "@/components/EmptyState";
import { CreateDebtForm, DebtList, StrategyComparisonView } from "@/features/debts";

export function Debts() {
  const { data: debts, isLoading } = useDebts();
  // Strategy comparison needs at least one debt; asking for it with none returns a
  // validation error, so the query is only enabled once there is something to compare.
  const { data: comparison } = useDebtStrategies();

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-title">Debts</h1>
      {isLoading ? <EmptyState message="Loading…" /> : <DebtList debts={debts ?? []} />}
      {comparison && (debts?.length ?? 0) > 1 ? (
        <StrategyComparisonView comparison={comparison} />
      ) : null}
      <CreateDebtForm />
    </div>
  );
}
