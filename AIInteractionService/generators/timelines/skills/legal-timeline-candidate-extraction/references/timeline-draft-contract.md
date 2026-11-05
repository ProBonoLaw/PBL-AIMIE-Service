# Timeline Draft Contract

This skill targets the supplied Pydantic models. `TimelineModel` uses a camel-case alias generator, accepts either Python field names or aliases during validation, and serializes by alias. Externally returned JSON therefore uses the camel-case names below.

## Top-level object

Return a `TimelineDraft`:

```json
{
  "originalRequest": "exact user request",
  "timeRange": {
    "startDate": "2026-03-01",
    "endDate": "2026-03-10"
  },
  "summary": "During March 2026, Smith submitted a complaint, HR investigated it, and management took the documented follow-up actions described in the entries.",
  "entries": [
    {
      "dateRange": {
        "startDate": "2026-03-05",
        "endDate": "2026-03-05"
      },
      "eventType": "Interview Conducted",
      "summary": "HR interviewed Jones regarding Smith's complaint.",
      "citationKeys": ["S1"]
    }
  ]
}
```

- `originalRequest` is required and must be the exact user request.
- `timeRange` has `default_factory=EventDateRange`. If omitted during validation, it becomes an `EventDateRange` whose `startDate` and `endDate` are both null. The timeline workflow should nevertheless return it explicitly as the overall supported span.
- `summary` is required. It is a detailed, evidence-grounded synthesis of the timeline. Aggregate its discussion by supported year or quarter when appropriate, but do not let that narrative aggregation replace the atomic event list.
- `entries` has `default_factory=list`, so the Pydantic model permits an empty list. For this workflow, use an empty list only when the returned records support no relevant event; otherwise include all supported atomic entries.

## Entry object

Each entry is a `TimelineEntryDraft`:

```json
{
  "dateRange": {
    "startDate": "2026-03-05",
    "endDate": "2026-03-05"
  },
  "eventType": "Interview Conducted",
  "summary": "HR interviewed Jones regarding Smith's complaint.",
  "citationKeys": ["S1"]
}
```

- `dateRange` has `default_factory=EventDateRange`. Emit it explicitly for every entry; use null boundaries when the supporting result is undated.
- `eventType` is a required string. The Pydantic model does not impose a controlled vocabulary, so use a narrow, stable, source-grounded category.
- `summary` is a required string describing one atomic occurrence. Preserve attribution for allegations, testimony, opinions, findings, and denials.
- `citationKeys` is required and enforces a minimum length of one.

Do not emit fields from `TimelineEntry`, including `applicableSources`. `TimelineSourceRegistry.resolve_timeline` converts each recognized `citationKey` into the corresponding canonical `ApplicableSource` after the draft is produced and rejects unknown citation keys.

## Date rules

`EventDateRange` accepts calendar precision `YYYY`, `YYYY-MM`, and `YYYY-MM-DD`, plus anonymized relative-year precision `YR-n`, `YR-n-MM`, and `YR-n-MM-DD`.

The retrieval layer converts source `whenStarted` and `whenEnded` metadata into each search result's `dateRange`, including any quarter or season expansion. Copy that returned range and its supported precision exactly. Do not:

- assign the document date to an undated reported occurrence;
- turn a month or year into a more precise day;
- derive a quarter or season yourself;
- make a broad period date the date of every entry it contains.

For a point event, use the provided point range. For a continuous state or activity, retain the provided start and end values.

When no date is supported, the canonical serialized value is:

```json
{
  "startDate": null,
  "endDate": null
}
```

An omitted `timeRange` or `dateRange` validates because of its default factory, but it resolves to this same `EventDateRange` value. Emit the object explicitly so the response contract remains consistent.

## Evidence and sources

- `citationKeys` must contain one or more citation keys supplied by records that directly support that entry. The current source registry generates opaque keys such as `S1`; treat the actual returned value as authoritative.
- Copy citation keys exactly. Do not create, modify, or infer them.
- Multiple keys are appropriate only when multiple supplied results support the same atomic occurrence.
- Do not attach a citation merely because it concerns the same participants, incident, or document.

## Aggregation guardrail

The `TimelineDraft.summary` field requires a detailed summary and asks for aggregation by time period, preferably at year or quarter level when appropriate. Apply that instruction only to the top-level summary—not to `entries`.

Entries remain the authoritative event-level record. Same date, source, event type, participant, incident, or calendar period does not establish that two actions are one entry.
