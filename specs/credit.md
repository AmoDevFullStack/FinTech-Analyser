# Credit profile

**Status: deferred to v2.** Specified now so the data model and interfaces anticipate it,
per `docs/requirements.md` section 15. Nothing here is built in v1.

## Objective

Incorporate the user's credit standing into financial health and affordability, using
bureau data rather than inference.

## Inputs

From a South African bureau — TransUnion, Experian, XDS, or Compuscan: score, score scale,
retrieval date, contributing factors, and account-level entries.

## Constraints that apply from now

- The system never estimates or infers a credit score. An unavailable score is absent, not
  approximated. A guessed score presented as a score is a specific and serious form of
  wrong.
- `CreditProfile` is nullable throughout and every consumer handles absence — the health
  engine, affordability checks, and the dashboard must all behave correctly with no credit
  data, which is the v1 case for every user.
- Bureau data is personal information under POPIA. Retrieval requires explicit consent,
  consent is recorded with a timestamp, and the data is retained no longer than necessary.
- Bureau retrieval sits behind an integration interface per `docs/architecture.md`. Services
  depend on the interface, never on a vendor SDK.
- The financial health score is not a credit score and is never described as one, whether
  or not bureau data is present.

## Anticipated behaviour

Score history and trajectory. Contributing factors mapped to the system's own health
components where they correspond. Affordability checks informed by likely lending rates at
the user's score band, with the band stated as an assumption.

## Acceptance criteria for v1

- [ ] The schema supports a credit profile without requiring one.
- [ ] Every consumer behaves correctly with no credit data present.
- [ ] No code path infers, estimates, or derives a credit score.
- [ ] The integration interface is defined even though no implementation exists.
