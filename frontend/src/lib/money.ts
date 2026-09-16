/**
 * The money boundary. See docs/frontend.md §4 and docs/architecture.md §4: the frontend
 * performs no financial calculations, and this file is the ONLY place a Money value may
 * be narrowed to a number — and only for formatting, never to produce a figure that is
 * then displayed as though the server had supplied it.
 *
 * `Number`, `parseFloat`, `parseInt`, and unary `+` on a Money value are forbidden
 * everywhere else in this tree (see .eslintrc.cjs's no-restricted-syntax block).
 */

declare const moneyBrand: unique symbol;
declare const rateBrand: unique symbol;

/** A monetary value exactly as the API sent it. Arithmetic on it does not compile. */
export type Money = string & { readonly [moneyBrand]: "Money" };

/** A rate or ratio exactly as the API sent it — same rule as Money. */
export type Rate = string & { readonly [rateBrand]: "Rate" };

/** Narrow a string known to have come from the API into a branded Money value. Call this
 * only at the API layer (see src/api/), never on a value typed elsewhere.
 */
export function asMoney(value: string): Money {
  return value as Money;
}

export function asRate(value: string): Rate {
  return value as Rate;
}

export function formatMoney(
  value: Money,
  { currency = "ZAR" }: { currency?: string } = {},
): string {
  const amount = Number(value);
  return new Intl.NumberFormat("en-ZA", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatRateAsPercent(value: Rate, { places = 1 }: { places?: number } = {}): string {
  const amount = Number(value) * 100;
  return `${amount.toFixed(places)}%`;
}

export function isNegative(value: Money): boolean {
  return value.trim().startsWith("-");
}

/** A rate narrowed to a 0–100 display width, e.g. for a utilisation bar. Clamped because a
 * visual bar has no meaningful way to render past full, unlike the percentage figure
 * itself (formatRateAsPercent), which is never clamped.
 */
export function rateAsPercentWidth(value: Rate, max = 100): number {
  const amount = Number(value) * 100;
  return Math.max(0, Math.min(amount, max));
}

/** A 0–100 score narrowed to a number for a gauge or meter. The API sends every Decimal
 * field as a string, score included, so this is subject to the same rule as Money and
 * Rate above: this file is the only place it may be parsed back to a number.
 */
export function scoreAsNumber(value: string): number {
  return Math.round(Number(value));
}
