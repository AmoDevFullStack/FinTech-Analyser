import { RecommendationList } from "@/features/recommendations";
import { RiskFlagList } from "@/features/risk";

export function Recommendations() {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-title">Worth knowing</h1>
      <RiskFlagList />
      <RecommendationList />
    </div>
  );
}
