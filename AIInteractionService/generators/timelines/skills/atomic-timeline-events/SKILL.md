---
name: atomic-timeline-events
description: Preserve atomic events rather than narrative aggregation in legal, investigative, and evidence-based timelines. Use when extracting, reviewing, or serializing records that may collapse distinct actions into a single event.
---

# Atomic Timeline Events

Represent the record at the smallest useful evidentiary resolution. The timeline must make it possible to reconstruct what happened without requiring the reader to reverse-engineer hidden steps from a summary.

## Core rule

An event entry represents one underlying occurrence: one action, decision, communication, observation, filing, encounter, finding, state transition, or continuous condition.

Do not merge distinct occurrences merely because they:

- appear in the same sentence, record, incident, meeting, day, or time period;
- involve the same person, organization, object, or case;
- use the same broad event category; or
- form an intuitive narrative or possible causal chain.

Treat a source's grouping as prose, not as the required timeline granularity.

## Split-or-merge decision

Start with one candidate for each event-bearing predicate. Split candidates when the record supports a difference in any of the following:

- primary act or state transition;
- actor, recipient, affected person, or object;
- date, time, location, or duration;
- procedural function, such as request, authorization, filing, service, ruling, or enforcement;
- evidentiary character, such as direct observation, allegation, testimony, denial, or finding;
- role in a sequence, such as complaint, investigation step, recommendation, decision, implementation, or response;
- independently supported consequence or later follow-on act.

Merge only when the available evidence supports that two statements describe the same underlying occurrence. Multiple sources may then corroborate one entry, but corroboration never justifies combining separate acts into a larger narrative event.

When identity is uncertain, preserve separate entries or candidates for later identity resolution. Do not resolve ambiguity by aggregation.

## Required handling patterns

### Compound accounts

Break a compound account into its supported parts. A sentence such as “officers stopped the vehicle, searched the trunk, found a laptop, seized it, and arrested Brown” normally contains five events, not one police encounter.

### Communications

Separate sending, receipt, acknowledgment, decision, and response when each is supported. A later response is not part of the original communication solely because it concerns the same subject.

### Document and case lifecycle

Treat creation, execution, filing, service, receipt, review, ruling, amendment, and disposition as separate events when supported. A document's date does not automatically date the occurrence it describes.

### Separate instruments and healthcare transitions

Treat issuance or execution of separate legal instruments as separate events, even when entered on the same date or described together. For example, a parenting plan or final parenting order is distinct from a dissolution decree unless the source establishes that they are one instrument.

Treat admission, emergency-department observation, evaluation, placement search, transfer, discharge, and release as distinct events when individually supported. A same-day admission and discharge remain separate state transitions; a multi-day observation record must not absorb its separately documented reevaluations or disposition efforts.

### Causal or procedural chains

Preserve intermediate steps. Do not compress `complaint → interview → findings → approval → termination` into a statement that the complaint caused the termination. Chronology alone does not prove causation.

### Accounts of prior events

Keep the reporting act distinct from the reported occurrence when both are material. For example, a deposition can support an event that testimony was given and a separate, source-qualified account of the earlier event described in testimony.

### Repeated versus continuous events

Use one range-based entry only for a genuinely continuous condition or activity supported as continuous. Separate repeated events and state changes, even when they occur in a short window.

### Contradictions and corrections

Do not merge incompatible accounts. Preserve each source-grounded account with its correct characterization. A correction, retraction, amendment, or denial is a separate event from the original assertion or action.

## Evidence discipline

- Attach only sources that directly support that single atomic entry.
- Preserve source date precision and uncertainty; do not use a broad period to absorb individually dated occurrences.
- State allegations, testimony, opinions, and findings as attributed claims rather than established fact.
- Do not infer a missing action, causal link, knowledge, intent, or consequence to make a sequence read smoothly.
- Do not make a separate entry from mere background detail unless it asserts a distinct occurrence relevant to the request.

Identify every independently occurring primary predicate in each proposed summary. If more than one remains, return the entry for decomposition. Multiple provisions of one order may remain together only when the entry represents the issuance of that order and the provisions are descriptive effects—not independently occurring acts or separately adjudicated issues.

## Anti-aggregation review

Before producing the timeline, review every entry:

1. Identify its primary predicate in a short phrase.
2. Ask whether another independently supported predicate is hidden in the same summary.
3. Ask whether the entry spans multiple dates, roles, procedural stages, or consequences that should be separate.
4. Confirm that all attached citations support this exact occurrence, not only its general subject.
5. If uncertain, favor preserving distinct entries over narrative compression.

Read [references/atomization-examples.md](references/atomization-examples.md) when records are compound, disputed, procedural, or difficult to divide.

## Output boundary

Follow the caller's required schema. Do not introduce internal identifiers or analytic fields that the schema does not allow. Apply atomicity within the available entry structure; keep potential-duplicate and relationship analysis internal or hand it to the designated downstream stage.

