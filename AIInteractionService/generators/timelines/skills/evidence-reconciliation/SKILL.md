---
name: evidence-reconciliation
description: Reconcile corroborating, conflicting, corrected, and differently precise accounts of legal-timeline events. Use after event identity and relationship analysis and before completeness review or serialization.
---

# Timeline Evidence Reconciliation

Produce an evidence-faithful representation of each resolved atomic event while preserving material disagreements. Reconciliation organizes the evidence; it does not decide the case.

## Boundaries

- Do not use source count as a proxy for truth.
- Do not rank credibility solely by document type, timestamp, authorship, or perceived authority unless the governing instructions provide that rule.
- Do not erase allegations, denials, amendments, or minority accounts to create a cleaner narrative.
- Do not combine conflicting occurrences merely because they concern the same incident.

## Evidence patterns

Treat sources as:

- corroborating when they support the same atomic occurrence without a material inconsistency;
- complementary when they support compatible aspects or different levels of detail;
- differently precise when one gives a broader date, time, location, or description that does not necessarily conflict;
- conflicting when they materially disagree about whether, when, where, how, or by whom an event occurred;
- corrective when a later source expressly amends, retracts, replaces, or corrects an earlier record;
- derivative when a source repeats another account rather than supplying independent support.

Do not characterize evidence as independent unless the returned records support that conclusion.

## Procedure

1. Work within identity-resolved event groups.
2. Break each source into claims about action, actor, object, date, location, characterization, outcome, and relationship.
3. Compare claims field by field rather than comparing only whole-record summaries.
4. Combine compatible claims into one neutral atomic entry and retain all directly supporting citation keys.
5. Preserve material conflicting accounts as separate attributed entries or as a carefully worded disputed entry when the distinction remains fully visible.
6. Represent a correction, amendment, retraction, denial, or superseding decision as its own event when it occurred separately.
7. Do not select a preferred account unless the evidence expressly establishes the resolution or the user asks for a supported credibility analysis.

## Wording rules

- State common supported facts directly.
- Attribute disputed content: `Smith alleged...`, `Jones denied...`, or `The report concluded...`.
- Preserve qualifiers and date precision.
- Do not use `confirmed`, `proved`, `admitted`, or similar terms unless the source supports that characterization.
- Avoid synthetic compromise wording that no source supports.

## Citations and `TimelineDraft`

For a reconciled `TimelineEntryDraft`, `citationKeys` contains every returned key that directly supports the entry's complete summary. Do not attach a contradictory source as support for a proposition it disputes; cite it to the separately attributed conflicting account instead.

Do not emit reconciliation status, credibility scores, source rankings, or claim matrices because those fields are absent from `TimelineDraft`. Preserve the evidentiary distinctions in the entry summaries and, when material, the top-level summary.

Before combining date or procedural discrepancies into one disputed entry, confirm that the disagreement concerns the same atomic occurrence rather than different lifecycle acts.

