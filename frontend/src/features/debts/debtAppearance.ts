import type { DebtType } from "@/api/types";

export const DEBT_TYPE_LABELS: Record<DebtType, string> = {
  credit_card: "Credit card",
  personal_loan: "Personal loan",
  vehicle: "Vehicle finance",
  home_loan: "Home loan",
  store_account: "Store account",
  other: "Other",
};

export const DEBT_TYPES: { value: DebtType; label: string }[] = (
  Object.keys(DEBT_TYPE_LABELS) as DebtType[]
).map((value) => ({ value, label: DEBT_TYPE_LABELS[value] }));

/** Debt types that run to a contractual end date, as opposed to a revolving facility.
 *
 * The distinction decides which amortisation engine the backend uses for the schedule
 * (`DebtService.schedule`), so the form asks for a term where one exists and says the
 * field is optional where one does not — rather than leaving the user to guess whether a
 * blank means "no term" or "not filled in yet".
 */
export const FIXED_TERM_TYPES: DebtType[] = ["vehicle", "home_loan", "personal_loan"];

export function isFixedTerm(debtType: DebtType): boolean {
  return FIXED_TERM_TYPES.includes(debtType);
}
