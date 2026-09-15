import type { ButtonHTMLAttributes } from "react";
import type { LucideIcon } from "lucide-react";

type Variant = "primary" | "secondary";

/** Liquid Glass per apple-design's `liquid-glass.md`: translucent fill, backdrop blur,
 * a hairline highlight border, colour reserved for the one prominent action per view
 * (primary) while secondary stays monochrome glass. Fixed white/accent-rgb values are
 * safe here because the app is forced to light appearance — see index.css. `--accent`
 * can't be used with Tailwind's `/opacity` modifier: that modifier only blends colours
 * Tailwind can decompose at build time, and `accent: "var(--accent)"` in tailwind.config
 * is an opaque CSS custom property to it, so `bg-accent/85` silently produced a fully
 * transparent fill (invisible white-on-white text) instead of an error.
 */
const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "border-white/40 bg-[rgba(28,63,110,0.85)] text-white shadow-[0_1px_3px_rgba(23,23,27,0.16)]",
  secondary:
    "border-white/60 bg-white/55 text-content shadow-[0_1px_3px_rgba(23,23,27,0.08)]",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: LucideIcon;
}

export function Button({ variant = "secondary", icon: Icon, className = "", children, ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex h-11 items-center justify-center gap-2 rounded-full border px-4 text-label font-medium backdrop-blur-xl backdrop-saturate-150 transition-colors duration-150 hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:pointer-events-none disabled:opacity-50 [@media(prefers-reduced-transparency:reduce)]:bg-surface-raised [@media(prefers-reduced-transparency:reduce)]:backdrop-blur-none ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    >
      {Icon ? <Icon size={18} strokeWidth={2} aria-hidden="true" /> : null}
      {children}
    </button>
  );
}
