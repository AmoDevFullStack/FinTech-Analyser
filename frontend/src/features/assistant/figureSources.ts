/** Plain words for where a figure came from.
 *
 * The server names the module that produced each figure — `emergency_fund_engine`,
 * `position_service` — which is exactly right for an audit trail and exactly wrong on a
 * screen. "from emergency_fund_engine" tells a reader nothing they wanted to know and
 * quite a lot about our file layout.
 *
 * The `source` on a figure stays as it was: it is the provenance ADR-002 requires, and it
 * is what a support conversation needs. Only the rendering changes.
 *
 * A `Record<string, string>` with a fallback rather than an exhaustive map over a union,
 * because these values are free-form strings on the wire — a new engine appearing
 * server-side must not put a raw module name on the screen, so the fallback is deliberately
 * vague rather than the key itself.
 */
const SOURCE_LABELS: Record<string, string> = {
  cash_flow_engine: "your cash flow",
  debt_payoff_engine: "your debt payoff plan",
  debt_repository: "your debts",
  emergency_fund_engine: "your emergency fund",
  emergency_fund_months: "your emergency fund",
  financial_health_engine: "your financial health score",
  forecast_engine: "your forecast",
  forecast_repository: "your saved forecast",
  forecast_service: "your forecast",
  goal_repository: "your goals",
  goals_engine: "your goals",
  intent_extraction: "your question",
  net_worth_engine: "your net worth",
  position_service: "where you stand today",
  projection_engine: "your projection",
};

/** What to show when the source is one this build has no words for. Vague on purpose:
 * "your figures" is true of anything the server can send, and is better than leaking a
 * module name onto the screen. */
const FALLBACK_LABEL = "your figures";

export function figureSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? FALLBACK_LABEL;
}
