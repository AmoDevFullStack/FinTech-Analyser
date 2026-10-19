import type { Money, Rate } from "@/lib/money";

/** A projected value and its provenance travel together — see docs/frontend.md §6 and
 * ADR-003. There is no code path that renders a bare projected value.
 */
export interface Projected<T> {
  value: T;
  generatedAt: string;
  isStale: boolean;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  currency: string;
  timezone: string;
}

export interface UpcomingObligation {
  label: string;
  amount: Money;
  due_on: string;
}

export interface HealthComponent {
  name: string;
  ratio: Rate;
  score: string;
  weight: string;
  contribution: string;
}

export interface HealthAssessment {
  /** The calendar month assessed, `YYYY-MM`. What the score is about — `computed_at` is
   * only when it was worked out. */
  month: string;
  score: number;
  computed_at: string;
  weights_version: string;
  components: HealthComponent[];
  largest_positive_contributor: string;
  largest_negative_contributor: string;
  /** Which inputs are the month's own and which are as they stand today. Null on
   * assessments stored before the score became month-by-month. */
  historical_basis: {
    monthly_flows: string;
    liquid_savings: string;
    debt_minimum_payments: string;
    credit_utilisation: string;
  } | null;
  /** How much statement evidence stands behind the score. Null on assessments stored
   * before the score became month-by-month. */
  evidence: {
    transactions_in_month: number;
    months_of_history: number;
    imports_behind_month: number;
  } | null;
}

export interface Position {
  as_of: string | null;
  net_worth: Money | null;
  liquid_savings: Money | null;
  total_debt: Money | null;
  monthly_income: Money | null;
  monthly_essential: Money | null;
  monthly_discretionary: Money | null;
  projected_cash_flow: Money | null;
  emergency_fund_months: string | null;
  /** The month the monthly figures above were measured over, `YYYY-MM` — the most recent
   * month with transactions, not necessarily the current one. Null before any snapshot has
   * recorded it. */
  baseline_month: string | null;
  /** How many months carry any transactions at all, and how many transactions there are.
   * A figure from one imported statement and a figure from eighteen are different claims. */
  months_of_history: number;
  transactions_counted: number;
  last_transaction_on: string | null;
  health_score: number | null;
  health_generated_at: string | null;
  health_score_change: number | null;
  health_largest_negative_contributor: string | null;
  upcoming_obligations: UpcomingObligation[];
  active_risk_flags: number;
  is_stale: boolean;
}

export type AccountType =
  | "transactional"
  | "savings"
  | "credit_card"
  | "loan"
  | "home_loan"
  | "vehicle_finance"
  | "investment"
  | "manual_asset";

export interface Account {
  id: string;
  name: string;
  account_type: AccountType;
  institution: string | null;
  current_balance: Money;
  balance_source: "derived" | "manual";
  is_manual_balance_stale: boolean;
  credit_limit: Money | null;
  utilisation: Rate | null;
  interest_rate: Rate | null;
  opened_on: string | null;
  archived_at: string | null;
}

/** How the money moved. Mirrors backend/app/domain/payment_taxonomy.py's PaymentMethod. */
export type PaymentMethod =
  | "debit_order"
  | "stop_order"
  | "card_purchase"
  | "card_online"
  | "atm_withdrawal"
  | "cash_deposit"
  | "eft_out"
  | "eft_in"
  | "instant_payment"
  | "internal_transfer"
  | "salary_deposit"
  | "cheque"
  | "bank_fee"
  | "interest"
  | "reversal"
  | "unknown";

/** What the payment was for. Mirrors that module's SpendingPurpose. */
export type SpendingPurpose =
  | "rent"
  | "bond_repayment"
  | "levies"
  | "rates_and_taxes"
  | "utilities"
  | "groceries"
  | "fuel"
  | "transport"
  | "vehicle_instalment"
  | "insurance"
  | "medical"
  | "telecoms"
  | "subscriptions"
  | "dining"
  | "entertainment"
  | "clothing"
  | "education"
  | "childcare"
  | "domestic_help"
  | "savings"
  | "investment"
  | "debt_repayment"
  | "bank_charges"
  | "salary"
  | "other_income"
  | "internal_transfer"
  | "unknown";

export type SpendKind = "income" | "essential" | "discretionary" | "debt" | "saving" | "transfer";

export interface Transaction {
  id: string;
  account_id: string;
  category_id: string | null;
  occurred_on: string;
  amount: Money;
  description: string;
  normalised_description: string;
  direction: "debit" | "credit";
  is_recurring: boolean;
  category_confidence: Rate | null;
  category_set_by_user: boolean;
  /** Null on a row imported before detection existed and never reclassified. The
   * interface renders the absence rather than showing "unknown", because "not looked at"
   * and "looked at and could not tell" are different claims. */
  payment_method: PaymentMethod | null;
  spending_purpose: SpendingPurpose | null;
  merchant: string | null;
  purpose_confidence: Rate | null;
  /** Present on search results only — how this row matched the query, not a property of
   * the row. See backend/app/repositories/transaction.py. */
  match_score?: Rate;
  match_basis?: "exact" | "fuzzy" | "filter";
}

/** One figure before and after a set of new transactions, with the movement between. */
export interface MetricChange {
  name: string;
  unit: "money" | "rate" | "months";
  before: string;
  after: string;
  delta: string;
  is_material: boolean;
}

export interface MonthlyFlows {
  income: Money;
  essential: Money;
  discretionary: Money;
  saving: Money;
  debt_service: Money;
}

export interface SpendingImpact {
  before: MonthlyFlows;
  after: MonthlyFlows;
  added: MonthlyFlows;
  changes: MetricChange[];
}

export interface DetectedRow {
  description: string;
  merchant: string | null;
  occurred_on: string;
  amount: Money;
  payment_method: PaymentMethod;
  spending_purpose: SpendingPurpose;
  kind: SpendKind | null;
  purpose_confidence: Rate;
  category_id: string | null;
  category_name: string | null;
  category_basis: string;
  is_duplicate: boolean;
  needs_review: boolean;
}

export interface GroupTotal {
  key: string;
  label: string;
  total: Money;
  monthly_average: Money;
  count: number;
}

export interface Commitment {
  label: string;
  merchant: string | null;
  method: PaymentMethod;
  purpose: SpendingPurpose;
  monthly_amount: Money;
  occurrences: number;
  is_new: boolean;
}

export interface AffectedArea {
  area: string;
  effect: string;
  detail: string;
}

export interface SpendingInsight {
  months_covered: number;
  period_start: string | null;
  period_end: string | null;
  rows_needing_review: number;
  rows: DetectedRow[];
  by_purpose: GroupTotal[];
  by_method: GroupTotal[];
  commitments: Commitment[];
  impact: SpendingImpact;
  affected: AffectedArea[];
}

export interface ScenarioPeriod {
  month: string;
  cash_flow: Money;
  savings: Money;
  debt: Money;
  net_worth: Money;
}

export interface ScenarioImpact {
  monthly_cash_flow_delta: Money;
  disposable_income_after: Money;
  debt_to_income_before: Rate;
  debt_to_income_after: Rate;
  emergency_fund_months_after: string;
  net_worth_at_60_months: Money;
  debt_free_date: string | null;
}

export interface Scenario {
  id: string;
  name: string;
  description: string | null;
  scenario_type: string;
  status: "draft" | "run";
  snapshot_captured_at: string;
}

export interface ScenarioResult {
  scenario_id: string;
  result_id: string;
  engine_version: string;
  computed_at: string;
  impact: ScenarioImpact;
  periods: ScenarioPeriod[];
  baseline_periods: ScenarioPeriod[];
}

export interface VehiclePurchaseAssumptions {
  purchase_price: string;
  deposit: string;
  annual_rate: string;
  term_months: number;
  insurance_monthly?: string;
  fuel_monthly?: string;
  maintenance_monthly?: string;
  trade_in_value?: string;
}

export type DebtType =
  | "credit_card"
  | "personal_loan"
  | "vehicle"
  | "home_loan"
  | "store_account"
  | "other";

export interface Debt {
  id: string;
  account_id: string | null;
  debt_type: DebtType;
  original_principal: Money;
  current_balance: Money;
  annual_rate: Rate;
  minimum_payment: Money;
  instalment: Money | null;
  term_months: number | null;
  started_on: string;
}

export interface SchedulePeriod {
  period: number;
  opening_balance: Money;
  instalment: Money;
  interest: Money;
  principal: Money;
  closing_balance: Money;
}

export interface WhatIfRow {
  extra_monthly: Money;
  months_to_free: number;
  total_interest: Money;
  months_saved: number;
  interest_saved: Money;
}

export interface StrategyResult {
  strategy: string;
  months_to_free: number;
  total_interest: Money;
  payoff_month_by_debt_id: Record<string, number>;
  schedule: {
    month: number;
    total_balance: Money;
    interest: Money;
    principal: Money;
    payment: Money;
  }[];
}

export interface StrategyComparison {
  avalanche: StrategyResult;
  snowball: StrategyResult;
  consolidation: StrategyResult | null;
  interest_difference_avalanche_vs_snowball: Money;
  months_difference_avalanche_vs_snowball: number;
  difference_is_material: boolean;
}

export interface Goal {
  id: string;
  name: string;
  account_id: string | null;
  target_amount: Money;
  target_date: string;
  priority: number;
  planned_monthly_contribution: Money | null;
}

export interface GoalProgress {
  goal: Goal;
  current_amount: Money;
  target_amount: Money;
  progress_source: "linked_account" | "contributions" | "none";
  months_remaining: number;
  required_monthly_contribution: Money;
  observed_monthly_rate: Money;
  projected_months: number | null;
  projected_achievement_date: string | null;
  is_achievable: boolean;
  monthly_shortfall: Money;
  date_slippage_months: number | null;
  annual_rate: Rate;
}

export interface FundingPlan {
  total_required: Money;
  available_cash_flow: Money;
  is_over_committed: boolean;
  fundings: {
    goal_id: string;
    priority: number;
    required_monthly: Money;
    funded_monthly: Money;
    is_fully_funded: boolean;
    slippage_months: number | null;
  }[];
}

export type RiskSeverity = "low" | "medium" | "high" | "critical";

export interface RiskFlag {
  id: string;
  risk_type: string;
  severity: RiskSeverity;
  status: "active" | "acknowledged" | "dismissed" | "resolved";
  detected_on: string;
  projected_date: string | null;
  quantified_amount: Money;
  explanation: string;
  computation_reference: string;
  details: Record<string, string>;
}

export interface RecommendationRow {
  id: string;
  rule_id: string;
  status: "active" | "dismissed" | "acted_on";
  benefit_amount: Money;
  benefit_kind: string;
  explanation: string;
  computation_reference: string;
  details: Record<string, string>;
  generated_on: string;
}

export interface ForecastPeriodRow {
  period_index: number;
  month: string;
  projected_income: Money;
  projected_expenses: Money;
  cash_flow: Money;
  savings_balance: Money;
  debt_balance: Money;
  emergency_fund_months: Rate;
  net_worth: Money;
}

export interface ForecastResponse {
  id: string;
  horizon_months: number;
  generated_at: string;
  is_stale: boolean;
  engine_version: string;
  input_snapshot_id: string;
  assumptions: Record<string, string>;
  is_low_confidence: boolean;
  months_observed: number;
  periods: ForecastPeriodRow[];
}

export interface AccuracySummaryRow {
  metric: string;
  months_measured: number;
  mean_absolute_error: Money;
  mean_percentage_error: Rate | null;
  has_persistent_bias: boolean;
  bias_direction: string | null;
  suggested_adjustment: Money;
}

export interface AccuracyResponse {
  measurements: {
    month: string;
    metric: string;
    projected: Money;
    actual: Money;
    absolute_error: Money;
    signed_error: Money;
    percentage_error: Rate | null;
    engine_version: string;
  }[];
  summaries: AccuracySummaryRow[];
}

export interface AssistantFigure {
  label: string;
  value: string;
  unit: string;
  source: string;
  result_id: string | null;
}

export interface AssistantAnswer {
  supported: boolean;
  answer: string | null;
  narration_available: boolean;
  figures: AssistantFigure[];
  based_on: { period?: string; assumptions?: Record<string, string> };
  clarification: string | null;
  capability: string;
  conversation_id: string | null;
}

/** GET /assistant/conversations and /assistant/conversations/{id} — docs/api.md §
 * "Assistant". A stored message keeps the figures it was answered with, so reopening a
 * conversation shows what was true when it was asked rather than recomputing silently.
 */
export interface AssistantConversationSummary {
  id: string;
  title: string | null;
  started_at: string;
}

export interface AssistantStoredMessage {
  id: string;
  asked_at: string;
  question: string;
  answer: string | null;
  capability: string;
  supported: boolean;
  narration_available: boolean;
  figures: AssistantFigure[];
}

export interface AssistantConversation extends AssistantConversationSummary {
  messages: AssistantStoredMessage[];
}

export interface RecurringSeriesRow {
  key: string;
  frequency: string;
  median_amount: Money;
  monthly_equivalent: Money;
  annual_cost: Money;
  occurrence_count: number;
  first_seen: string;
  last_seen: string;
  next_expected_on: string;
  category_id: string | null;
  category_kind: string | null;
}

/** GET /transactions/months — docs/api.md § "Month by month".
 *
 * Two views of the same month, and they answer different questions. `totals` excludes
 * internal transfers, because moving money between your own accounts is neither income
 * nor spending. `cash` includes them, because a balance does not care why money left —
 * it is the figure that reconciles to a bank statement.
 */
export interface MonthTotals {
  income: Money;
  essential: Money;
  discretionary: Money;
  saving: Money;
  debt_service: Money;
  /** Everything that left, saving included: a month that put money away had that much
   * less available. */
  spending: Money;
  /** income − spending. Negative in a month that overspent, and shown as such. */
  net: Money;
}

export interface MonthMetricChange {
  previous: Money;
  current: Money;
  change: Money;
  /** Null when last month was zero — from nothing to something has no percentage, and a
   * 0% would read as "unchanged". */
  percentage_change: Rate | null;
}

export interface MonthCash {
  opening: Money;
  inflow: Money;
  outflow: Money;
  closing: Money;
}

export type MonthMetric = keyof MonthTotals;

export interface MonthReport {
  /** `YYYY-MM`. */
  month: string;
  previous_month: string | null;
  totals: MonthTotals;
  changes: Partial<Record<MonthMetric, MonthMetricChange>>;
  /** Null when nothing in scope holds a cash balance, such as a credit card on its own. */
  cash: MonthCash | null;
  transaction_count: number;
  /** The uploads this month's figures were built from. Empty for a month entered by hand. */
  import_batch_ids: string[];
}

export interface MonthlySummaryResponse {
  data: MonthReport[];
  months: number;
}
