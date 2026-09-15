/** Component keys as stored by app/domain/financial_health.py -> display copy. Shared by
 * the dashboard's health region and the full-breakdown page so the two never drift.
 */
export const HEALTH_COMPONENT_LABELS: Record<string, string> = {
  emergency_cover: "Emergency fund covers too few months of essential spending",
  debt_burden: "Debt obligations take up a large share of income",
  cash_flow_margin: "Little is left over after essential and discretionary spending",
  savings_rate: "Little of income is being saved",
  credit_utilisation: "Credit balances are high relative to their limits",
  cash_flow_stability: "Month-to-month cash flow varies a lot",
};

export function healthComponentLabel(name: string): string {
  return HEALTH_COMPONENT_LABELS[name] ?? name.replace(/_/g, " ");
}
