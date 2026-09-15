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
        signal: {
          caution: "var(--signal-caution)",
          critical: "var(--signal-critical)",
          positive: "var(--signal-positive)",
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
