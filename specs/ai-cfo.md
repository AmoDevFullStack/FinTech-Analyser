# AI CFO

## Objective

Let a user ask a financial question in their own words and get an answer grounded entirely
in their own computed figures.

## The boundary

The model never computes a financial figure. It receives computed results and turns them
into language. This is ADR-002 and it is not negotiable — it is the reason the product's
numbers can be trusted at all.

## Inputs

A natural-language question, and optionally a conversation identifier for follow-ups.

## Processing

**1. Intent classification.** Map the question to a supported capability: affordability
check, scenario request, position query, spending analysis, debt question, goal question,
forecast question, or explanation of a figure already shown.

Where no capability matches, return unsupported. Do not approximate. "I can't model that
yet" is a recoverable failure; a confident wrong number is not.

**2. Parameter extraction.** Pull the figures and timeframe from the question — R15,000, in
December. Where a required parameter is missing, ask for it rather than assuming.

**3. Context assembly.** Load only the verified financial data the capability needs, from
result objects rather than raw rows. A spending question does not need the user's debt
schedule.

**4. Engine execution.** Run the relevant engine or scenario. This produces the figures.

**5. Narration.** Send the model the question, the computed result object, and response
constraints. The model composes prose over figures it has been given.

**6. Return** both: the structured figures with their engine provenance, and the narration.
The figures are authoritative; the narration is presentation.

## Worked example

*"Can I afford a R15,000 holiday in December?"*

Intent: affordability check. Parameters: R15,000, December 2026. Context: position
snapshot, current forecast for December, emergency fund coverage, upcoming obligations.
Engine: discretionary expense scenario. Result: cash flow after, emergency cover after,
obligations still covered.

Narration: what the figures mean, what it costs in emergency cover, and what would change
if it were R10,000 or moved to January — each of those alternatives also computed, not
guessed.

## Constraints

- The model may not compute, estimate, or infer a figure.
- The model may not query the database or call a tool that writes.
- Every figure in the response carries its engine and result identifier.
- No model output is persisted to a financial field, asserted by test.
- With the provider unavailable, figures return with `answer: null` and the client renders
  them unnarrated.
- Only the minimum financial context required is sent to the provider.
- Responses never state or imply financial advice. "Here is what it costs" is in scope;
  "you should not do this" is not.
- Follow-up questions re-run the pipeline. Figures are never carried forward from
  conversation history, because the underlying position may have changed.

## Acceptance criteria

- [ ] Intent classification covers the supported capabilities with an explicit unsupported path.
- [ ] Missing parameters trigger a clarifying question rather than an assumption.
- [ ] Every returned figure carries engine and result provenance.
- [ ] A test asserts no model output is written to a financial column.
- [ ] Provider unavailability returns figures without narration.
- [ ] Unsupported questions say so and name what is missing.
- [ ] Prompt payloads are built from result objects, never raw rows.
- [ ] Prompt-injection attempts in transaction descriptions cannot alter a returned figure.
