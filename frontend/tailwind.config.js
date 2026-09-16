/** Tokens lifted verbatim from docs/design-system.md §2–3. No hard-coded colours in
 * components — every colour a component uses must be one of these names.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "var(--surface)",
          raised: "var(--surface-raised)",
          sunken: "var(--surface-sunken)",
        },
        content: {
          DEFAULT: "var(--content)",
          secondary: "var(--content-secondary)",
          tertiary: "var(--content-tertiary)",
        },
        rule: {
          DEFAULT: "var(--rule)",
          meaning: "var(--rule-meaning)",
        },
        accent: "var(--accent)",
        scrim: "var(--scrim)",
        signal: {
          caution: "var(--signal-caution)",
          critical: "var(--signal-critical)",
          positive: "var(--signal-positive)",
        },
        score: {
          poor: "var(--score-poor)",
          fair: "var(--score-fair)",
          good: "var(--score-good)",
        },
      },
      fontFamily: {
        ui: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        1: "var(--shadow-1)",
        2: "var(--shadow-2)",
        3: "var(--shadow-3)",
      },
      backgroundImage: {
        glass: "linear-gradient(to bottom, var(--glass-raised), var(--glass-raised))",
      },
      keyframes: {
        // §7: 120-200ms, ease-out, and never blocking input. The drawer animates in on
        // mount; it unmounts on close, because a drawer that stays mounted keeps its
        // links in the accessibility tree whatever CSS says about visibility.
        "drawer-in": {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(0)" },
        },
        "drawer-in-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
      },
      animation: {
        "drawer-in": "drawer-in 200ms cubic-bezier(0.32, 0.72, 0, 1)",
        "drawer-in-right": "drawer-in-right 200ms cubic-bezier(0.32, 0.72, 0, 1)",
      },
      transitionTimingFunction: {
        // §7: 120-200ms, ease-out. Named so no component invents its own curve.
        exit: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      fontSize: {
        position: ["2.5rem", { lineHeight: "1.1", fontWeight: "500" }],
        "figure-lg": ["1.75rem", { lineHeight: "1.2", fontWeight: "500" }],
        figure: ["1.25rem", { lineHeight: "1.3", fontWeight: "500" }],
        title: ["1.25rem", { lineHeight: "1.3", fontWeight: "600" }],
        body: ["1rem", { lineHeight: "1.5", fontWeight: "400" }],
        label: ["0.875rem", { lineHeight: "1.4", fontWeight: "500" }],
        caption: ["0.8125rem", { lineHeight: "1.4", fontWeight: "400" }],
      },
    },
  },
  plugins: [],
};
