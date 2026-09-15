import { RiskFlagList } from "@/features/risk";

/** Region 5 — active risk flags. Per specs/dashboard.md this region is ABSENT (not a
 * green all-clear) when there are none, so it never trains the user to skim past it.
 * RiskFlagList returns null in that case, which is what makes the region disappear.
 *
 * It renders each flag's own explanation, which the server composed to the spec's copy
 * conventions, rather than the count this used to show: a count tells the user something
 * is wrong without telling them what or when.
 */
export function AttentionRegion() {
  return <RiskFlagList />;
}
