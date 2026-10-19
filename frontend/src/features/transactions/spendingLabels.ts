import type { PaymentMethod, SpendKind, SpendingPurpose } from "@/api/types";

/** Human labels for what the detection engine returns.
 *
 * Kept as an exhaustive `Record` rather than a lookup with a fallback: adding a member to
 * `PaymentMethod` or `SpendingPurpose` in backend/app/domain/payment_taxonomy.py without
 * giving it a label here is then a type error at build time, instead of a raw
 * `bond_repayment` appearing in the interface.
 */
export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  debit_order: "Debit order",
  stop_order: "Stop order",
  card_purchase: "Card purchase",
  card_online: "Online card",
  atm_withdrawal: "ATM withdrawal",
  cash_deposit: "Cash deposit",
  eft_out: "EFT out",
  eft_in: "EFT in",
  instant_payment: "Instant payment",
  internal_transfer: "Transfer",
  salary_deposit: "Salary deposit",
  cheque: "Cheque",
  bank_fee: "Bank fee",
  interest: "Interest",
  reversal: "Reversal",
  unknown: "Unrecognised",
};

export const SPENDING_PURPOSE_LABELS: Record<SpendingPurpose, string> = {
  rent: "Rent",
  bond_repayment: "Bond repayment",
  levies: "Levies",
  rates_and_taxes: "Rates and taxes",
  utilities: "Utilities",
  groceries: "Groceries",
  fuel: "Fuel",
  transport: "Transport",
  vehicle_instalment: "Vehicle instalment",
  insurance: "Insurance",
  medical: "Medical",
  telecoms: "Telecoms",
  subscriptions: "Subscriptions",
  dining: "Dining out",
  entertainment: "Entertainment",
  clothing: "Clothing",
  education: "Education",
  childcare: "Childcare",
  domestic_help: "Domestic help",
  savings: "Savings",
  investment: "Investment",
  debt_repayment: "Debt repayment",
  bank_charges: "Bank charges",
  salary: "Salary",
  other_income: "Other income",
  internal_transfer: "Transfer",
  unknown: "Not recognised",
};

export const SPEND_KIND_LABELS: Record<SpendKind, string> = {
  income: "Income",
  essential: "Essential",
  discretionary: "Discretionary",
  debt: "Debt service",
  saving: "Saving",
  transfer: "Transfer",
};

/** Labels for the impact report's metric names, in the order the report reads best.
 *
 * Order is defined here rather than taken from the response because the useful reading
 * order is editorial: the money figures first, the ratios derived from them after, and
 * emergency-fund cover last because it is the one that moves for a reason the user has to
 * be told (essential spending is its denominator).
 */
export const IMPACT_METRIC_LABELS: Record<string, string> = {
  monthly_income: "Monthly income",
  monthly_essential: "Essential spending",
  monthly_discretionary: "Discretionary spending",
  monthly_saving: "Saving",
  monthly_debt_service: "Debt repayments",
  monthly_cash_flow: "Monthly surplus",
  liquid_savings: "Liquid savings",
  cash_flow_margin: "Cash-flow margin",
  savings_rate: "Savings rate",
  debt_to_income: "Debt to income",
  emergency_fund_months: "Emergency fund cover",
};

export const IMPACT_METRIC_ORDER: string[] = [
  "monthly_income",
  "monthly_essential",
  "monthly_discretionary",
  "monthly_debt_service",
  "monthly_saving",
  "monthly_cash_flow",
  "cash_flow_margin",
  "savings_rate",
  "debt_to_income",
  "emergency_fund_months",
];
