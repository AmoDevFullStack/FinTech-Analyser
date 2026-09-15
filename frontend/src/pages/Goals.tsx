import { useGoals } from "@/api/goals";
import { EmptyState } from "@/components/EmptyState";
import { CreateGoalForm, FundingPlanView, GoalProgressCard } from "@/features/goals";

export function Goals() {
  const { data: goals, isLoading } = useGoals();

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-title">Goals</h1>

      {isLoading ? <EmptyState message="Loading…" /> : null}

      {goals && goals.length > 0 ? (
        <>
          <FundingPlanView />
          {goals.map((goal) => (
            <GoalProgressCard key={goal.id} goal={goal} />
          ))}
        </>
      ) : isLoading ? null : (
        <EmptyState message="No goals yet. A goal here is measured against what your money actually does, not against what you plan to contribute." />
      )}

      <CreateGoalForm />
    </div>
  );
}
