# Design system

This file is the visual source of truth for the Financial Digital Twin. Read it before
adding a component, choosing a colour, or deciding how a figure appears on screen. Where
this file and the interface disagree, this file wins and the interface is a bug.

Structure lives in `docs/frontend.md`. Behaviour lives in `specs/`. Decisions that should
not be casually reversed live in `docs/decisions.md`. This file describes appearance and
the rules that govern it.

**Provenance.** The rules below are derived from Apple's Human Interface Guidelines,
vendored at `.claude/skills/apple-design/references/hig/`. This product is a web
application, so Apple's *platform conventions* — tab bars, sheets, the menu bar, safe
areas — do not apply and are not cited. Apple's *foundations* — accessibility, colour,
typography, layout, writing, charting — do apply, and are cited as `file.md › Heading`
where a rule comes from them. Anything not cited is a judgment call and says so.

---

## 1. The organising idea

Every number in this product has a lineage. It was computed by a named engine, at a known
time, from stored assumptions, and it is either something that *happened* or something
that is *modelled*. `specs/dashboard.md` requires that "projected and actual figures are
visually distinguishable, not merely labelled", and forbids encoding financial status in
colour alone. ADR-003 requires that a projection always discloses when it was generated.

So the design's single job is this: **make the certainty of a figure legible before the
figure is read.**

That is the one thing this interface should be remembered by. It is not decoration — it is
the visual form of the product's central claim, that its numbers are trustworthy because
you can see where they came from. Everything else is deliberately quiet so that this
distinction has room to register.

Consequences of taking that seriously:

- Certainty is never carried by colour, because colour is reserved for signal and must
  survive colour blindness and greyscale.
- Colour is scarce. Spending it on decoration leaves none for meaning.
- There is one typeface. Hierarchy comes from weight, size, and space.

---

## 2. Colour

Tokens are named by role, never by appearance, so they can be redefined per appearance
without renaming. `color.md › System colors`: "Each dynamic color is semantically defined
by its purpose, rather than its appearance or color values."

Contrast figures below are computed WCAG ratios against the stated surface, not estimates.

### 2.1 Light

| Token | Value | On `surface` | Use for |
|---|---|---|---|
| `--surface` | `#FCFCFB` | — | Page ground |
| `--surface-raised` | `#FFFFFF` | — | Cards, panels, popovers |
| `--surface-sunken` | `#F1F1EE` | — | Table header rows, inset wells |
| `--content` | `#17171B` | 17.41:1 | Primary text, figures |
| `--content-secondary` | `#56565F` | 7.07:1 | Labels, supporting text |
| `--content-tertiary` | `#6F6F78` | 4.85:1 | Timestamps, axis ticks, captions |
| `--rule` | `#E3E3DD` | 1.26:1 | Decorative separators only |
| `--rule-meaning` | `#8E8E87` | 3.21:1 | Rules that carry information |
| `--accent` | `#1C3F6E` | 10.30:1 | Interactive elements, focus ring |
| `--signal-caution` | `#8A5A00` | 5.77:1 | Caution state, always with a label |
| `--signal-critical` | `#9B2C24` | 7.36:1 | Critical state, always with a label |
| `--signal-positive` | `#1F5D3F` | 7.59:1 | Direction of a delta, nothing else |

### 2.2 Dark

**Currently disabled in code.** The app is forced to light appearance regardless of the
OS/browser setting — see §10. The table below is kept as the reference palette for if
dark appearance is re-enabled later.

| Token | Value | On `surface` | Use for |
|---|---|---|---|
| `--surface` | `#121316` | — | Page ground |
| `--surface-raised` | `#1A1B1F` | — | Cards, panels, popovers |
| `--surface-sunken` | `#0D0E10` | — | Table header rows, inset wells |
| `--content` | `#F2F2F0` | 16.57:1 | Primary text, figures |
| `--content-secondary` | `#A8A8B2` | 7.88:1 | Labels, supporting text |
| `--content-tertiary` | `#8E8E98` | 5.73:1 | Timestamps, axis ticks, captions |
| `--rule` | `#2C2D33` | 1.35:1 | Decorative separators only |
| `--rule-meaning` | `#686973` | 3.41:1 | Rules that carry information |
| `--accent` | `#8FB4E8` | 8.72:1 | Interactive elements, focus ring |
| `--signal-caution` | `#E0A93B` | 8.76:1 | Caution state, always with a label |
| `--signal-critical` | `#E88A80` | 7.41:1 | Critical state, always with a label |
| `--signal-positive` | `#6BBF8F` | 8.38:1 | Direction of a delta, nothing else |

Dark surfaces are not inverted light surfaces. `dark-mode.md › Dark Mode colors`: "these
colors aren't necessarily inversions of their light counterparts".

**One documented shortfall.** `dark-mode.md › Dark Mode colors` advises striving for 7:1
on custom colours, "especially in small text". `--content-tertiary` in dark reaches
5.73:1. It clears the 4.5:1 floor in `accessibility.md › Vision` but not the 7:1
aspiration, so it is restricted: never below 15px, and never the only carrier of essential
information. Raising it further collapses its distinction from `--content-secondary`,
which would cost more hierarchy than it buys contrast.

### 2.3 Rules that govern colour

**One colour means one thing.** `color.md › Best practices`: "Avoid using the same color to
mean different things." `--accent` means interactive. It is never used to decorate a
non-interactive figure.

**Nothing is conveyed by colour alone.** `color.md › Inclusive color`: "Avoid relying
solely on color to differentiate between objects, indicate interactivity, or communicate
essential information." Every signal colour appears with a text label and a shape. A
caution state is an amber dot *and* the word describing it.

**`--signal-positive` is the token most likely to be abused.** It marks the direction of a
change, never the quality of a financial position. `specs/dashboard.md` deliberately omits
a green all-clear because it "trains the user to skim past it". Do not reintroduce one.

**No hard-coded colour values anywhere.** Every colour is a token. A hex value in a
component is a bug.

---

## 3. Typography

**One typeface.** `typography.md › Conveying hierarchy`: "Minimize the number of typefaces
you use, even in a highly customized interface. Mixing too many different typefaces can
obscure your information hierarchy." Hierarchy comes from weight, size, and space.

```css
--font-ui: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
           "Helvetica Neue", Arial, sans-serif;
```

The personality of this product lives in the certainty treatment of section 5, not in a
display face. A second typeface would compete with the one distinction that matters.

### 3.1 Scale

Sizes are `rem`, never `px`, so the interface responds to the reader's browser text size.
This is the web equivalent of Dynamic Type, which `typography.md › Supporting Dynamic Type`
requires: "Make sure your app's layout adapts to all font sizes."

| Style | Size | Weight | Line height | Use for |
|---|---|---|---|---|
| `position` | 2.5rem / 40px | 500 | 1.1 | The three anchor figures only |
| `figure-lg` | 1.75rem / 28px | 500 | 1.2 | Section-leading figures |
| `figure` | 1.25rem / 20px | 500 | 1.3 | Figures in cards and rows |
| `title` | 1.25rem / 20px | 600 | 1.3 | Region headings |
| `body` | 1rem / 16px | 400 | 1.5 | Running text, table cells |
| `label` | 0.875rem / 14px | 500 | 1.4 | Field labels, column headers |
| `caption` | 0.8125rem / 13px | 400 | 1.4 | Timestamps, axis ticks, provenance |

**Floor: 13px.** Nothing essential renders below 14px. `accessibility.md › Vision` sets
the macOS minimum at 10 pt against a fixed viewing distance and Apple's own rendering; the
browser default of 16px is the honest web equivalent of its 13 pt default, and 13px is the
corresponding floor.

**Avoid light weights.** `typography.md › Ensuring legibility`: "prefer Regular, Medium,
Semibold, or Bold font weights, and avoid Ultralight, Thin, and Light font weights". The
scale above uses 400, 500, and 600 only.

### 3.2 Figures

**All figures use tabular lining numerals.** `font-variant-numeric: tabular-nums` on every
element that renders money, a rate, or a count. Proportional figures make columns of money
fail to align, which is the single most legible signal that a financial interface was built
carelessly. This is a judgment call, not an Apple guideline.

**Money is right-aligned in tables, left-aligned in prose.** Comparison down a column
requires a shared decimal position.

**Money arrives as a string and is never parsed into a number for arithmetic.** See ADR-001
and `docs/frontend.md` §4. Formatting for display is not calculation.

---

## 4. Space and layout

An 8px base unit. Tokens: `--space-1` 4px, `--space-2` 8px, `--space-3` 12px, `--space-4`
16px, `--space-6` 24px, `--space-8` 32px, `--space-12` 48px.

**Group related items, and give essential information room.** `layout.md › Best practices`:
"Make essential information easy to find by giving it sufficient space. People want to view
the most important information right away, so don't obscure it by crowding it with
nonessential details."

**Reading order carries importance.** `layout.md › Visual hierarchy`: "it generally works
well to place the most important items near the top and leading side". The dashboard's five
regions appear in the priority order `specs/dashboard.md` sets and are not reordered by
viewport.

Breakpoints, and what changes at each:

| Width | Layout |
|---|---|
| < 640px | Single column. Position figures stack. Tables become labelled rows. |
| 640–1023px | Two columns. Position figures in a row of three. |
| ≥ 1024px | Content column capped at 1200px. Regions may sit side by side. |

**Layouts survive the largest text size.** At 200% text, regions stack to one column and
figures wrap beneath their labels rather than truncating. `typography.md › Supporting
Dynamic Type`: "Keep text truncation to a minimum as font size increases."

**Targets are at least 44×44px** with at least 8px between adjacent controls.
`accessibility.md › Mobility` sets 44×44 pt as the touch default and treats spacing as
"as important as size". Applying the touch figure rather than the pointer figure across the
board costs nothing on desktop and removes a class of error on tablets.

---

## 5. The certainty scale

This is the signature element. It is used once, consistently, everywhere a figure appears.

| State | Treatment |
|---|---|
| **Actual** | `--content`, weight 500. No rule. Nothing added. |
| **Projected** | `--content`, weight 500, with a 1px `--rule-meaning` basis line beneath the figure, offset 4px. The region carries `Projected as of <date>` in `caption`/`--content-tertiary`. |
| **Stale** | Projected treatment, plus a `Stale` chip — outlined, with a shape, not a colour fill — and a visible **Refresh** action. |
| **Hypothetical** | Projected treatment. The region header carries the scenario's snapshot date, per ADR-005. |

The basis line is borrowed from the ruled line drawn under a derived figure in a ledger,
where it has meant "this was computed, not observed" for about as long as double-entry
bookkeeping has existed. It is the product's own vernacular rather than a borrowed visual
idiom.

It survives greyscale, colour blindness, and forced-colours mode, because it is geometry
rather than hue. That is why it, and not a colour, carries the distinction.

Rules:

- **One date per region, not per figure.** `specs/dashboard.md` requires every projected
  figure to carry its generation date; rendering it on each figure individually produces
  noise that trains people to ignore it. The region owns the date; every figure in the
  region shares it.
- **A projection rendered without its date is a bug**, per `docs/api.md`.
- **The basis line is never used decoratively.** If a rule appears under a figure, that
  figure is modelled. No exceptions — the moment it appears anywhere else it stops meaning
  anything.
- **`--rule` and `--rule-meaning` are not interchangeable.** Decorative separators use
  `--rule` and may sit below 3:1. Anything that carries information uses `--rule-meaning`
  and clears 3:1.

---

## 6. Charts

`specs/dashboard.md` warns that the failure mode of a financial dashboard "is not being too
sparse; it is being a wall of charts nobody reads twice". A chart appears only where it
answers a question a table cannot.

**Mark types**, per `charts.md › Marks`: bars for comparison across categories and for
values that represent a sum per period; lines for change over time; points for individual
values, outliers, and clusters. Cash flow is a flow, not a proportion — `specs/dashboard.md`
requires it "rendered as a flow, not a pie chart". There are no pie charts in this product.

**Projection is drawn differently from history.** Actual periods are solid; projected
periods are dashed and sit after a labelled boundary marking today. The baseline comparison
that `docs/api.md` returns alongside every scenario result is drawn as a second, lighter
line, directly labelled. This is section 5 applied to chart marks.

**Series are limited to four**, and each is identified by direct label and by mark shape or
dash pattern *before* colour. `charts.md › Color`: "Avoid relying solely on color to
differentiate between different pieces of data... One way to supplement color is to use
different shapes or patterns." The series palette is a luminance ladder so it also survives
greyscale:

| Slot | Light | On surface | Dark | On surface |
|---|---|---|---|---|
| 1 | `#16324F` | 12.76:1 | `#A8C7F0` | 10.70:1 |
| 2 | `#6E3A78` | 8.06:1 | `#E0A066` | 8.31:1 |
| 3 | `#A8571B` | 5.06:1 | `#4FA3A3` | 6.28:1 |
| 4 | `#3F8A8A` | 3.92:1 | `#A06FB2` | 4.79:1 |

Four is a cap, not a default. Five hues that each clear 3:1 against the surface *and*
remain separable in greyscale is not achievable; a fifth series means the chart should be
split, not that the palette should grow.

**Axes.** Bar charts start at zero. Line charts of a quantity that never approaches zero —
net worth, a balance — use a dynamic lower bound, per `charts.md › Axes`: "defining a lower
bound of zero can sometimes make meaningful differences between values more difficult to
discern." Where a dynamic bound is used, say so in the axis label; a truncated axis that
does not announce itself overstates the change.

**Every chart states its conclusion in words.** `charting-data.md › Designing effective
charts`: "Descriptive text titles, subtitles, and annotations help emphasize the most
important information in a chart and can highlight actionable takeaways."

**Every chart is reachable without sight or a pointer.** `charts.md › Best practices`: "don't
require interaction to reveal critical information." Each chart ships a table equivalent
reachable from the chart itself. Accessible names describe what a mark represents, not what
it looks like, and avoid subjective words — `charts.md › Enhancing the accessibility of a
chart`: "Subjective words — like rapidly, gradually, and almost — communicate your
interpretation of the data."

---

## 7. Motion

Motion is rare here. Transitions are 120–200ms, ease-out, and never block input.

`accessibility.md › Cognitive` requires an answer to Reduce Motion: under
`prefers-reduced-motion: reduce`, transforms and positional animation are replaced with
opacity fades or removed, and no animation is the only indication that something changed.

A number that changes never counts up. An animated figure is unreadable while it animates,
and in a product whose claim is precision it reads as showmanship.

---

## 8. States

**Loading.** Something appears immediately. Skeletons match the shape of what is arriving so
the layout does not jump. Where work is genuinely slow — a scenario run, per ADR-003 —
progress is specific about what is happening, not a generic spinner.

**Empty.** Every region has one, per `specs/dashboard.md`. `writing.md › Best practices`:
"An empty screen can be daunting if it isn't obvious what to do next, so guide people on
actions they can take, and give them a button or link to do so if possible." An empty
region names the one action that fills it.

**Absent.** Distinct from empty. The attention region is *removed* when there are no risk
flags rather than showing an all-clear, per `specs/dashboard.md`.

**Error.** Rendered next to the thing that failed, never as a modal. `writing.md › Best
practices`: "avoid blame, and be clear about what someone can do to fix it". No apologies,
no "oops", no `we`. "Unable to load your position. Retry." not "We're sorry, something went
wrong!"

---

## 9. The AI CFO surface

ADR-002 makes the boundary between computed figures and generated prose the product's
central claim. The interface has to show that boundary, not just respect it.

**Figures and narration are visually separate.** `docs/api.md` states that `figures` is
authoritative and `answer` is narration over it. The figures render as figures, with the
certainty treatment of section 5 and their engine attribution available. The prose renders
as prose, clearly marked as generated.

**Disclose the generated part.** `generative-ai.md › Transparency`: "Never trick someone
into thinking they're interacting with or viewing content authored by a human if they're
actually interacting with AI."

**When the provider is unavailable, the numbers still render.** `docs/api.md` returns
`answer: null` with `narration_available: false`, and the UI shows the figures without
apology. `generative-ai.md › Best practices`: "When possible, consider offering a non-AI
fallback." Here the fallback is the entire point.

**When no engine can answer, say what cannot be modelled.** `supported: false` renders as a
statement of the system's limits, never as an approximation. `generative-ai.md › Outputs`:
"Help people improve requests when blocked or undesirable results occur."

**Generation feedback is specific.** `generative-ai.md › Outputs`: "instead of
'Processing…', say 'Finding substitutions for ingredients'". Here: "Running the affordability
engine", then "Writing the explanation" — which also makes the two-stage boundary visible
while the user waits.

---

## 10. Appearance

**Currently: light only, forced.** The app ignores `prefers-color-scheme` — there is no
dark variant in `index.css`, by explicit product decision. This is a deliberate deviation
from both the guideline below and from ADR-007's recommendation; §2.2 keeps the dark
palette on record for if that decision is revisited.

`dark-mode.md › Best practices` says to "avoid offering an app-specific appearance setting",
because it competes with the system preference. On the web that guidance collides with a
real constraint: `prefers-color-scheme` reports the browser's setting, which on shared,
locked-down, or managed machines the reader frequently cannot change.

**Standing recommendation (not current behaviour):** a three-state control — System,
Light, Dark — defaulting to System, and placed in settings rather than the main interface.
This honours the system preference by default while not stranding the reader who has no
way to set it. The token structure means the override costs nothing beyond the control
itself. Recorded as ADR-007.

---

## 11. The floor

No interface ships below this line.

- [ ] Every text token clears 4.5:1 against every surface it is used on. Verified by
      computation, not by eye.
- [ ] Nothing essential is conveyed by colour alone.
- [ ] Layouts survive 200% text with hierarchy intact and no truncation of essential text.
- [ ] Targets are at least 44×44px with at least 8px between them.
- [ ] Keyboard focus is visible on every interactive element, using `--accent` at ≥3:1
      against its surface, and never removed without an equally visible replacement.
- [ ] Every interactive element is reachable and operable by keyboard alone.
- [ ] Every icon-only control has an accessible name.
- [ ] `prefers-reduced-motion` is respected and no meaning is carried by motion alone.
- [ ] The (currently sole) light appearance is tested at increased contrast and with
      Reduce Transparency, since Button now renders a Liquid Glass surface.
- [ ] Every chart has a table equivalent.
- [ ] Every projected figure shows its generation date.

The first and last items are the ones specific to this product. The first is where generic
dashboards fail; the last is where this one would stop being trustworthy.
