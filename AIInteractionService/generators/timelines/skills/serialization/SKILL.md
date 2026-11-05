---
name: serialization
description: Serialize a completed legal-timeline analysis as the application's `TimelineDraft` Pydantic response. Use only after event extraction, identity resolution, relationship analysis, gap analysis, evidence reconciliation, and completeness review.
---

# Timeline Serialization

Convert the completed, evidence-reviewed atomic event set into `TimelineDraft`. Serialization must preserve the analysis without adding, merging, or reinterpreting facts.

## Exact response model

Return one `TimelineDraft` object. `TimelineModel` accepts Python field names and aliases, but serialized output uses camelCase:

```json
{
  "originalRequest": "exact user request",
  "timeRange": {
    "startDate": "2026-03-01",
    "endDate": "2026-03-10"
  },
  "summary": "Evidence-based orientation to the timeline.",
  "entries": [
    {
      "dateRange": {
        "startDate": "2026-03-01",
        "endDate": "2026-03-01"
      },
      "eventType": "complaint submitted",
      "summary": "Smith submitted a complaint to HR.",
      "citationKeys": ["C12"]
    }
  ]
}
```

Do not return `TimelineResult`. Do not emit `sessionId`, `accountId`, `timeToCompletionSeconds`, `applicableSources`, `docId`, `sourceId`, `url`, or `pages`. The service resolves `citationKeys` into `ApplicableSource` objects after receiving the draft.

## Top-level fields

### `originalRequest`

Copy the user's request exactly. Do not paraphrase, normalize, correct, or shorten it.

### `timeRange`

Set the supported chronological envelope of the returned entries:

- `startDate` is the earliest supported start among comparable dated entries.
- `endDate` is the latest supported end among comparable dated entries.
- Preserve `YYYY`, `YYYY-MM`, `YYYY-MM-DD` precision.
- Do not invent missing months or days to calculate the envelope.
- Do not compare calendar dates with anonymized relative years unless the record supplies a mapping.
- Use null values when no supported overall boundary can be expressed.

### `summary`

Provide an evidence-based orientation to the timeline. It may synthesize major periods, patterns, supported relationships, or disputes, including year- or quarter-level organization when helpful.

Aggregation is allowed in the top-level summary only. It must not reduce, merge, replace, or omit atomic entries. Preserve attribution and uncertainty; do not introduce facts or conclusions absent from the entries and their evidence.

### `entries`

Include every material, supported atomic event that survived completeness review. Use an empty list only when the returned records support no relevant event.

## Entry fields

Every entry contains exactly:

- `dateRange`: the source-supported `EventDateRange`; use null values when undated;
- `eventType`: a narrow, stable, human-readable category describing the primary action or state; use spaces, never snake_case or camelCase;
- `summary`: one neutral atomic occurrence, with attribution for allegations, testimony, opinions, denials, or findings;
- `citationKeys`: a non-empty list copied exactly from results directly supporting the complete entry summary.

Every listed citation must directly support every substantive clause in that entry. Never use an order, filing, or finding as support for the occurrence of a hearing unless it expressly reports the hearing; never use a hearing record as support for an order-entry clause unless it expressly records the order. If no citation directly supports a clause, search for direct support, narrow the clause, or omit the entry.

Do not add internal candidate IDs, participant arrays, relationship fields, gap flags, confidence scores, evidence-status fields, or `footnotes`. The service moves entries whose `dateRange` has neither a `startDate` nor an `endDate` into final-result `footnotes`.

## Ordering

Place entries in chronological order using only supported date information.

- Preserve distinct entries that share the same date.
- For ties, use a supported time or procedural sequence when available; otherwise use a stable order without implying causation.
- Do not force a partially dated event ahead of a more precise event when their relative order is unsupported.
- Place undated events where a source-supported sequence establishes their position; otherwise place them after dated events and make the lack of a supported date clear.
- Do not mix relative-year and calendar-date axes into a false total order.

## Final validation

Before returning:

1. Confirm the object validates as `TimelineDraft`.
2. Confirm `originalRequest` is exact.
3. Confirm every relevant entry is atomic and every `citationKeys` list is non-empty.
   * For each proposed entry, identify its primary predicate.

      Reject or return the entry for decomposition if:

      * its summary asserts two or more independently occurring primary actions;
      * a date range contains repeated point events rather than one continuous state;
      * plural occurrences such as three visits, multiple calls, or several hearings have been collapsed despite individually supported occurrences being available;
      * one entry combines request, ruling, implementation, and consequence;
      * one entry combines separate lifecycle acts such as execution, filing, service, receipt, and disposition.

      An entry may contain multiple descriptive facts about the same occurrence.
4. Confirm dates use allowed precision and no missing components were invented.
5. Confirm the top-level time range encloses, but does not broaden, all comparable dated entries.
6. Confirm no prohibited fields or Markdown wrappers are present.

Return only the structured response required by the caller.

Confirm that completeness review resolved every referenced material issue-lifecycle endpoint. Do not serialize while an endpoint remains unresolved.

