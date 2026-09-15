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
