/** The no-restricted-syntax block enforces docs/frontend.md §4: Number/parseFloat/
 * parseInt/unary-plus on a Money value are forbidden everywhere outside src/lib/money.ts.
 * ESLint can't see the Money brand itself, so this bans the four narrowing operations
 * process-wide except in the one file that is allowed to use them, via an override below.
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended", "plugin:react-hooks/recommended"],
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: "latest", sourceType: "module", ecmaFeatures: { jsx: true } },
  plugins: ["@typescript-eslint", "react-hooks"],
  ignorePatterns: ["dist", "node_modules"],
  rules: {
    "no-restricted-syntax": [
      "error",
      {
        selector: "CallExpression[callee.name='Number']",
        message: "Number() is forbidden outside src/lib/money.ts — see docs/frontend.md §4.",
      },
      {
        selector: "CallExpression[callee.name='parseFloat']",
        message: "parseFloat() is forbidden outside src/lib/money.ts — see docs/frontend.md §4.",
      },
      {
        selector: "CallExpression[callee.name='parseInt']",
        message: "parseInt() is forbidden outside src/lib/money.ts — see docs/frontend.md §4.",
      },
      {
        selector: "UnaryExpression[operator='+']",
        message: "Unary + is forbidden outside src/lib/money.ts — see docs/frontend.md §4.",
      },
    ],
  },
  overrides: [
    {
      files: ["src/lib/money.ts"],
      rules: { "no-restricted-syntax": "off" },
    },
    {
      files: ["**/*.test.ts", "**/*.test.tsx", "src/test/**"],
      env: { node: true },
    },
  ],
};
