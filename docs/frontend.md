# Frontend architecture

This file is the structural source of truth for `frontend/`. Read it before adding a file,
moving logic between layers, or introducing a dependency. Where this file and the code
disagree, this file wins and the code is a bug.

It is the frontend counterpart to `docs/architecture.md`, which governs the backend and
remains authoritative for the system as a whole. Appearance lives in
`docs/design-system.md`. Behaviour lives in `specs/`. The HTTP contract lives in
`docs/api.md`.

---

## 1. The organising idea

The backend is a deterministic core surrounded by surfaces. The frontend is one of those
surfaces, and it is the furthest from the truth. It computes nothing and it invents
nothing. Its entire job is to render, accurately and legibly, figures that arrived from
somewhere else.

```
pages/            route composition
    ↓
features/         capability modules — components + hooks, colocated
    ↓
api/              the only place HTTP happens
    ↓
(network)
```

`components/`, `hooks/`, and `lib/` are shared leaves. Any layer may use them; they depend
on nothing above themselves.

Every dependency arrow points downward. A shared component never imports from `features/`.
A feature never imports another feature's internals. `lib/` imports nothing from the
application at all.

---

## 2. Layout

```
frontend/src/
├── pages/          route-level compositions, one file per route
├── features/       one folder per capability
│   └── scenarios/
│       ├── components/
│       ├── hooks/
│       └── index.ts        the feature's entire public surface
├── components/     shared presentational components
├── api/            typed client, generated types, query definitions
├── hooks/          shared hooks with no feature knowledge
└── lib/            formatting, dates, display-only helpers
```

Feature folders match the files in `specs/`: `accounts`, `transactions`, `dashboard`,
`scenarios`, `forecasting`, `debts`, `goals`, `health`, `risk`, `assistant`,
`recommendations`. When a spec exists, the feature folder carries its name.

A feature exposes only what `index.ts` exports. Reaching into
`features/scenarios/components/AssumptionRow` from another feature is a bug; if two
features need the same component, it belongs in `components/`.

---

## 3. Layer contracts

### 3.1 `api/`

The only layer permitted to perform network I/O. It owns the typed client, the response
types, and the query and mutation definitions. No other layer calls `fetch`.

Types are written against `docs/api.md` and are not hand-adjusted to match observed
responses. If the server disagrees with the types, one of them is wrong and the
disagreement is resolved before the code merges — the same rule the backend's contract
tests enforce from the other side.

Must not contain: rendering, formatting for display, or business conditionals.

### 3.2 `features/`

A capability, colocating its components, hooks, and types. This is where most code lives.

A feature may call `api/`, use `components/`, `hooks/`, and `lib/`, and export a small
public surface. It may not import another feature's internals, and it may not perform
arithmetic on a monetary value.

### 3.3 `components/`

Shared, presentational, and unaware of where data came from. A shared component receives
values through props, renders them, and raises events.

Must not contain: imports from `api/` or `features/`, data fetching, or knowledge of any
specific capability.

### 3.4 `lib/`

Pure functions for display: currency formatting, date formatting, number formatting,
pluralisation. No React, no network, no application state.

`lib/money.ts` is the single place in the frontend permitted to narrow a `Money` value.
See section 4.

### 3.5 `pages/`

Route composition only. A page assembles features into a layout and owns nothing else. A
page that contains a conditional about a financial value has logic in the wrong place.

---

## 4. Money on the client

`docs/architecture.md` §4 states the rule: the frontend performs no financial
calculations, and money crosses the wire as a string so precision survives the trip. This
section makes that rule mechanically enforceable rather than a matter of discipline.

Money is a branded string. It is not `number`, and it is not plain `string`:

```ts
declare const brand: unique symbol;

/** A monetary value as it arrived from the API. Never arithmetic. See ADR-001. */
export type Money = string & { readonly [brand]: 'Money' };
```

Because `Money` is a string, arithmetic on it does not compile. Because it is branded, a
plain string cannot be passed where a `Money` is expected, so values cannot drift in from
form inputs or literals without passing through `lib/money.ts`.

What remains possible, and is therefore forbidden by rule and by lint: `Number(value)`,
`parseFloat(value)`, `parseInt(value)`, and `+value`. These are permitted nowhere outside
`lib/money.ts`, and inside it only for formatting — never to produce a figure that is then
displayed as though the server had supplied it.

Formatting is not calculation. `formatMoney(value, { currency: 'ZAR' })` is display.
`formatMoney(a) + formatMoney(b)` is a bug, and so is anything that computes a total, a
difference, a percentage, or a projected balance. If a figure is needed and the API does
not return it, the fix is an endpoint, not a client-side sum.

Rates and ratios follow the same rule and arrive as strings, per `docs/api.md`.

---

## 5. Server state

Server state is cached and owned by TanStack Query. Local UI state — a form's contents, a
disclosure's open state, a selected tab — uses `useState` or `useReducer` in the component
that owns it. There is no global client store, and adding one requires an ADR.

The reason this works is ADR-003. The server already materialises everything the client
reads; responses are stored results, not derivations computed per request. A cache of
server responses is therefore a cache of the truth, and there is no second source of state
to reconcile it against. Recorded as ADR-006.

Query keys mirror the API's resource structure: `['position']`, `['scenarios', id]`,
`['scenarios', id, 'results']`. The dashboard issues exactly one query, `['position']`,
per `specs/dashboard.md`.

Mutations invalidate the queries their endpoint's write affects, and nothing wider.
`POST /scenarios/{id}/run` invalidates that scenario's results; it does not invalidate
`['position']`, because running a scenario does not touch real state, per ADR-005.

Mutations that create financial state send an `Idempotency-Key`, per `docs/api.md`.

---

## 6. Certainty in the type system

ADR-003's staleness contract and `docs/api.md`'s rule — "a client that renders a projection
without its generation date is a client bug" — are enforced structurally rather than left to
review.

A projected value and its provenance travel together as one object, so a component cannot
receive the figure without also receiving the date:

```ts
export type Projected<T> = {
  value: T;
  generatedAt: string;   // RFC 3339
  isStale: boolean;
};
```

Components that render a `Projected<Money>` render the certainty treatment in
`docs/design-system.md` §5. There is no code path that renders `projected.value` alone,
because the display components take the wrapper, not the field.

Scenario results carry their snapshot date the same way, per ADR-005.

---

## 7. Routing

Routes map to `pages/`, one file each. Every route is reachable by URL and survives a
reload, including a scenario's result view — a projection a user wants to return to or send
to someone else is not transient state.

Money, dates, and identifiers appear in URLs as they do in the API: identifiers are UUIDs,
dates are `YYYY-MM-DD`.

---

## 8. Testing

| What | How |
|---|---|
| Shared components | Vitest, rendered, behaviour asserted through the accessibility tree |
| Feature hooks | Vitest with a mocked `api/` layer |
| Money formatting | Vitest, against the same reference figures the backend engines use |
| Certainty rendering | Vitest — a projected figure without its date must fail a test |
| Contract conformance | Types generated or checked against `docs/api.md` |
| End to end | Playwright: scenario creation through result display |

Query by role and accessible name rather than by test id, so the tests fail when the
interface stops being operable by assistive technology. This makes the accessibility floor
in `docs/design-system.md` §11 a test failure rather than a review comment.

---

## 9. Dependencies

`docs/architecture.md` §5: no new dependency without an entry in `docs/decisions.md`. That
applies here. The frontend's dependency set is React, TypeScript, Vite, Tailwind, TanStack
Query (ADR-006), and a charting library still to be chosen — which will need its own ADR,
assessed primarily on whether it can produce the accessible table equivalent and the
non-colour series encoding that `docs/design-system.md` §6 requires.

---

## 10. When you are about to add something

- Does it perform arithmetic on money? → It does not belong in the frontend at all.
- Does it fetch? → `api/`
- Is it specific to one capability? → `features/<capability>/`
- Is it used by two or more features? → `components/` or `hooks/`
- Is it a pure display transform? → `lib/`
- Does it assemble a route? → `pages/`

If the answer is "several of these", it is several things and should be split.

If the change contradicts this file, update this file in the same pull request and add an
ADR if it reverses a recorded decision. Do not leave the document and the code
disagreeing.
