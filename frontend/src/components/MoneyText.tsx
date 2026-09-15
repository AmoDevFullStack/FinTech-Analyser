import { formatMoney, type Money } from "@/lib/money";

/** Renders a Money value. This is the one place a Money value becomes a number, and it
 * happens inside formatMoney (src/lib/money.ts), never here.
 */

// Full class names written out literally so Tailwind's source scanner can find them —
// a template-interpolated `text-${size}` is invisible to the JIT compiler.
const SIZE_CLASSES = {
  position: "text-position",
  "figure-lg": "text-figure-lg",
  figure: "text-figure",
  body: "text-body",
} as const;

export function MoneyText({
  value,
  className = "",
  size = "figure",
}: {
  value: Money;
  className?: string;
  size?: keyof typeof SIZE_CLASSES;
}) {
  return (
    <span className={`font-ui tabular-nums ${SIZE_CLASSES[size]} ${className}`}>
      {formatMoney(value)}
    </span>
  );
}
