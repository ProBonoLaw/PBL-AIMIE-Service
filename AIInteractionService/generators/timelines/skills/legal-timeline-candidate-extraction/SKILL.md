---
name: legal-timeline-candidate-extraction
description: Extract atomic, source-supported candidate events from retrieved case records for a legal or investigative timeline. Use before event identity resolution, causal-link analysis, deduplication, or final timeline serialization.
---

# Legal Timeline Candidate Extraction

Extract a high-recall set of candidate events from the evidence returned by the case-search tools. In this application, candidates serialize as `TimelineDraft.entries` using `TimelineEntryDraft`; they are atomic evidentiary entries, not compressed narrative periods.

## Governing boundary

- Treat search results as the sole source of case facts.
- Do not use the filesystem or claim to have reviewed records that a search tool did not return.
- Never invent an event, actor, date, source, quotation, motive, state of mind, legal conclusion, or relationship.
- Preserve whether a source presents something as documented fact, testimony, allegation, opinion, or inference.
- Follow the caller's output schema and provenance field names when they conflict with examples in this skill. The model contract for this service is documented in [references/timeline-draft-contract.md](references/timeline-draft-contract.md).
- Do not decide ultimate truth, liability, credibility, relevance, or legal significance during candidate extraction.

## Search for candidate-bearing evidence

Use `search_case_events` first for event-focused requests. Use `search_case_context` only when needed to resolve a referenced person, alias, document, location, date, case identifier, or surrounding statement that may reveal another supported event.

Search deliberately across the user's requested scope. Vary queries when necessary to cover:

- people, aliases, titles, organizations, and relationships;
- actions, communications, decisions, observations, filings, encounters, and state changes;
- dates, date ranges, locations, document names, quotations, and reference numbers;

- procedural steps, notice, authorization, response, consequence, and disputed accounts.

Treat offense names, allegation categories, and investigative labels as umbrella
retrieval concepts rather than literal phrases. For a domestic-violence scope,
the application runs deterministic searches for direct terminology, physical
conduct, high-risk threats, coercion and stalking, police and protective-order
records, and injury, safety, and child-exposure records before this stage. Use
the returned records and coverage context as retrieval leads, then search
specific incidents or references that need clarification. These cues are not
findings: do not call conduct domestic violence, abuse, a crime, or a legal
violation unless a source or adjudication directly supports that label.

Do not stop after finding a plausible narrative. Continue until the returned evidence has been examined for materially distinct occurrences and targeted follow-up searches no longer reveal new candidate-bearing records within the task's scope.

## Extract event assertions before composing a narrative

Read each returned record at clause level. Identify every passage that asserts or reports a potentially material occurrence. Convert each occurrence into a candidate before attempting to summarize the case.

An atomic candidate normally contains one primary predicate: one action, occurrence, decision, communication, observation, filing, encounter, omission supported as an event, or change in state.

Split a passage into separate candidates when the evidence supports materially different:

- actions or state transitions;
- actors or recipients;
- objects or affected persons;
- dates, times, or locations;
- procedural or legal functions;
- evidentiary characterizations;
- roles in a possible event chain, such as request, approval, implementation, discovery, or response;
- consequences that occurred as their own supported event.

Do not merge events merely because they occur on the same date, appear in one sentence or record, share an actor, use the same event type, or belong to one larger incident.

Keep an act and its later reporting separate. For example, testimony that an earlier meeting occurred may support a candidate for the alleged meeting and a separate candidate for the testimony itself when both matter to the requested scope. Characterize each according to the source.

Keep these separately when independently supported:

- creation, filing, service, receipt, review, and disposition of a document;
- request, authorization, implementation, and resulting action;
- sending, receipt, acknowledgment, and response to a communication;
- complaint, investigation step, finding, recommendation, decision, and enforcement action;
- medical complaint, examination, diagnosis, treatment, and follow-up;
- observation, search, discovery, seizure, arrest, booking, and release.

Use a date range for one candidate only when the source supports a genuinely continuous state or activity. Do not use a broad range to compress separately dated occurrences.

## Prefer recall over premature deduplication

Candidate extraction is intentionally recall-first. When two assertions may describe the same underlying occurrence but identity is uncertain, preserve both as separate candidates and flag the possible match for downstream event identity resolution.

Do not combine candidates merely because their summaries are semantically similar. Only a later identity-resolution or deduplication stage should determine that multiple records describe the same atomic event.

Repeated wording within one record need not create multiple candidates when it plainly repeats the same assertion without adding a distinct act, time, participant, characterization, or consequence.

## Preserve evidence character

Write neutral summaries that identify who did what, to whom or what, and when, but only to the precision supported by the record.

- Attribute allegations and testimony to the speaker or filing.
- Preserve qualifiers such as `reported`, `estimated`, `approximately`, `denied`, or `disputed` when material.
- Do not turn a source's conclusion into an independently established fact.
- Do not infer causation from chronology, proximity, shared participants, or thematic similarity.
- Record an express relationship statement as evidence for later analysis; do not independently validate the relationship during this stage.
- Treat silence as no evidence of an event. Extract a failure to act only when the returned material affirmatively supports the duty or expected action and the nonoccurrence.

## Preserve dates and provenance

Use each result's supplied `dateRange` exactly. Do not add missing date components, convert an undated assertion into the document date, or substitute the date of reporting for the date of the reported occurrence.

For every candidate:

- retain every `citationKey` that directly supports that candidate assertion;
- never copy or invent `docId` or `sourceId` values;
- do not attach a citation merely because it concerns the same person, incident, or subject;
- distinguish the occurrence date from the record, filing, or reporting date when both are supported.

Do not use `ApplicableSource`, `docId`, `sourceId`, `url`, or `pages` in this agent's draft output. Those fields are resolved by the service after it maps each `citationKey` to a canonical source.

## Output contract

Return the application's `TimelineDraft` shape. The serialized JSON aliases are camelCase:

```yaml
originalRequest: the user's request copied exactly
timeRange:
  startDate: overall supported start, or null
  endDate: overall supported end, or null
summary: brief evidence-based orientation; never a substitute for the entries
entries:
  - dateRange:
      startDate: exact supplied date component, or null
      endDate: exact supplied date component, or null
    eventType: narrow, source-grounded, human-readable category
    summary: one atomic occurrence, neutrally stated
    citationKeys: non-empty list of directly supporting search-result keys
```

Each entry must conform to `TimelineEntryDraft`: only `dateRange`, `eventType`, `summary`, and `citationKeys`. Do not emit internal fields such as candidate IDs, participants, evidence-character labels, possible-duplicate flags, relationship leads, source IDs, or page numbers.

Express evidentiary character inside the source-grounded summary when needed. For example, write `Rivera testified that she observed ...` or `The complaint alleges ...`; do not add an undeclared `evidenceCharacter` field.

Use a narrow, stable, human-readable `eventType` such as `Complaint submitted`, `Interview conducted`, `Motion filed`, `Order issued`, `Email sent`, `Property seized`, or `Treatment provided` when the caller has not defined a controlled vocabulary. Use spaces, never snake_case or camelCase. Do not use an event type so broad that it hides the supported action.

`timeRange` is an envelope for the returned entries, not a permission to broaden individual event dates. Derive it only from comparable, source-supported entry dates. If the records do not support a meaningful overall span, retain the schema's null values rather than inventing a span.

The model's `summary` field is an orientation only. It may identify major themes, periods, or disputes, but must not merge, replace, or omit atomic entries. Do not restate every event in the summary, and do not use period-level grouping as a reason to aggregate entries.

## Coverage review

Before handing candidates to the next stage, verify:

1. Every event-bearing clause in the relevant results was either represented by a candidate or deliberately excluded as repetition, non-event background, or unsupported interpretation.
2. No candidate summary contains multiple independently supported primary actions that should be split.
3. No distinct event was absorbed into another because it shared a date, actor, document, incident, or category.
4. Every entry has at least one direct `citationKey` and preserves the source's evidentiary characterization in its summary.
5. Dates retain the precision and uncertainty supplied by the source.
6. Potential duplicates, contradictions, relationship statements, and unresolved references are preserved for downstream review rather than silently resolved.


## Handoff

Maintain the candidate set internally in a form compatible with TimelineEntryDraft: dateRange, eventType, summary, and directly supporting citationKeys.

Do not produce or serialize the final TimelineDraft during candidate extraction. Final serialization occurs only in timeline-serialization after all downstream stages have completed.

The downstream stages should perform event identity resolution, corroboration, contradiction analysis, causal-link analysis, gap searching, materiality review, chronological ordering, and final schema serialization.
