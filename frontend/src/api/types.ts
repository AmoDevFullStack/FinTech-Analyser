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
  score: number;
  computed_at: string;
  weights_version: string;
  components: HealthComponent[];
  largest_positive_contributor: string;
  largest_negative_contributor: string;
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
