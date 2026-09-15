import {
  Car,
  CreditCard,
  Gem,
  Home,
  Landmark,
  PiggyBank,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import type { AccountType } from "@/api/types";

/** One icon per account type — icons.md › Best practices: "use icons consistently, and
 * pair each with a text label" (labels come from ACCOUNT_TYPE_META.label, never the icon
 * alone).
 */
export const ACCOUNT_TYPE_META: Record<AccountType, { label: string; icon: LucideIcon }> = {
  transactional: { label: "Transactional", icon: Wallet },
  savings: { label: "Savings", icon: PiggyBank },
  credit_card: { label: "Credit card", icon: CreditCard },
  loan: { label: "Loan", icon: Landmark },
  home_loan: { label: "Home loan", icon: Home },
  vehicle_finance: { label: "Vehicle finance", icon: Car },
  investment: { label: "Investment", icon: TrendingUp },
  manual_asset: { label: "Manual asset", icon: Gem },
};

export const ACCOUNT_TYPES = Object.keys(ACCOUNT_TYPE_META) as AccountType[];

/** Types specs/accounts.md describes as "interest-bearing or credit accounts". */
export const INTEREST_BEARING_TYPES: AccountType[] = [
  "savings",
  "credit_card",
  "loan",
  "home_loan",
  "vehicle_finance",
  "investment",
];

export const CREDIT_LIMIT_TYPES: AccountType[] = ["credit_card"];
