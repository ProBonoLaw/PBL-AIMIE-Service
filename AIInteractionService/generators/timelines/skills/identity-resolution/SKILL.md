---
name: identity-resolution
description: Resolve whether legal-timeline candidates describe the same event, different events, or unresolved possible matches. Use after atomic candidate extraction and before evidence reconciliation or serialization.
---

# Timeline Identity Resolution

Determine which candidate assertions refer to the same underlying atomic occurrence without erasing distinct events. Resolve event identity first and participant identity only when needed to make that decision.

## Boundaries

- Use only facts and identifiers supplied by the case-search results.
- Do not infer that two people, organizations, documents, or events are identical from name similarity alone.
- Do not decide credibility, legal effect, causation, or ultimate truth during this stage.
- Do not emit identity-analysis fields that are absent from `TimelineDraft` or `TimelineEntryDraft`.

## Event identity test

Compare candidates using an event fingerprint:

- primary action or state change;
- actor and affected person, recipient, or object;
- supported date, time, and duration;
- location or procedural setting;
- referenced document, communication, transaction, or incident;
- event outcome and role in the surrounding sequence;
- source characterization, including whether the occurrence is alleged, observed, testified to, denied, or formally found.

Merge candidates only when the evidence supports that they describe the same underlying occurrence. Missing details do not prove identity. Semantic similarity, the same date, the same participants, or the same broad event type is insufficient by itself.

Differences may be compatible when one source is less precise or supplies additional detail. Treat differences as material when they indicate a different act, actor, recipient, object, occurrence time, procedural stage, outcome, or evidentiary characterization.

## Participant and document identity

Resolve aliases, titles, abbreviations, maiden names, organizational units, and document references only when the returned material supplies a reliable connection. Preserve ambiguity when two possible identities remain.

Do not treat a title such as “the supervisor,” a common surname, or an organization name as a unique identifier without contextual support. Do not merge original, amended, corrected, attached, or refiled documents merely because their titles are similar.

## Procedure

1. Group only candidates that plausibly share an event fingerprint.
2. Compare every material fingerprint element and the supporting citations.
3. Classify each group internally as `same occurrence`, `distinct occurrences`, or `unresolved`.
4. For `same occurrence`, retain one atomic event and combine all directly supporting citation keys without duplication.
5. For `distinct occurrences`, preserve separate events even if the summaries are similar.
6. For `unresolved`, keep separate candidates for later reconciliation or targeted searching; do not force a merge.
7. Recheck that merging did not hide a request, authorization, implementation, response, correction, or consequence as part of another event.

## Handoff to `TimelineDraft`

Pass the resolved atomic event set to the next stage. When eventually serialized, each `TimelineEntryDraft` contains only `dateRange`, `eventType`, `summary`, and non-empty `citationKeys`.

Do not expose fingerprints, group IDs, confidence scores, or identity classifications in the response. Express unresolved material differences in the source-grounded summaries only when they are relevant to the requested timeline.

