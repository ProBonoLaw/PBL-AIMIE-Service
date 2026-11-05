---
name: completeness-review
description: Audit a legal timeline for omitted supported events, lost intermediate steps, unresolved evidence issues, provenance defects, and schema violations. Use immediately before final serialization.
---

# Timeline Completeness Review

Perform a final evidence-coverage audit before serialization. Completeness means complete treatment of the relevant returned record within the user's requested scope; it does not mean claiming knowledge of the entire real-world case.

## Coverage audit

Verify that:

- every relevant event-bearing clause is represented or deliberately excluded as repetition, background, or unsupported interpretation;
- compound narratives have been decomposed into atomic events;
- same-day, same-document, same-participant, and same-incident events were not merged without event-identity support;
- identity resolution did not absorb a distinct request, approval, implementation, response, correction, or consequence;
- material intermediate events discovered during gap analysis are included;
- material conflicts, denials, corrections, and alternative accounts remain visible;
- each event has at least one citation key directly supporting its full summary;
- dates preserve the source's precision and do not borrow document or neighboring-event dates;
- relationship wording does not overstate chronology, allegation, or inference as causation;
- the event set answers the user's actual request rather than merely summarizing the available documents.

For every material issue identified during the workflow:

1. Confirm that its major supported initiation, material interim changes, and supported disposition are represented.
2. Confirm that a later order or decision referenced by earlier evidence was either located or subjected to a targeted search.
3. Confirm that the timeline does not end an issue at an interim ruling when returned or discoverable evidence identifies a later final disposition.
4. Confirm that every category expressly requested by the user was searched proportionately—for example hearings, discovery, emergencies, CPS/child welfare, and noteworthy occurrences.
5. Do not require a lifecycle stage merely because such a stage normally exists.

## Issue-lifecycle gate

Maintain or consume an internal ledger of every material issue identified during the workflow.

For each material issue:

1. Identify its earliest supported initiation.
2. Identify each significant supported intermediate change.
3. Identify its latest supported disposition.
4. Determine whether the returned evidence expressly references another initiation, ruling, implementation, or disposition that is not represented.
5. Route any referenced but unrepresented lifecycle event to gap analysis for targeted searching.

Classify each referenced lifecycle endpoint internally as:

- `represented`;
- `outside_user_scope`;
- `searched_not_supported`; or
- `unresolved`.

Do not proceed to serialization while any referenced material lifecycle endpoint remains `unresolved`.

Do not require or invent a lifecycle stage merely because that stage ordinarily occurs. A matter may remain pending, and the indexed evidence may not contain a final disposition.

When targeted searches do not support the referenced event, mark it `searched_not_supported` and preserve any material limitation for the top-level summary. Do not create a placeholder timeline entry.

## Search closure

When tools remain available, perform narrowly targeted searches for unresolved references that could reveal a material event. Route newly found evidence back through candidate extraction, atomic decomposition, identity resolution, relationship analysis, and reconciliation.

Stop when additional targeted searches yield no materially distinct supported events or relationship evidence within scope. Do not treat search closure as proof that no other evidence exists.

### Document-lifecycle closure

When a retained event expressly references a later implementing or dispositive document, confirm that the referenced document was:

- represented by its supported lifecycle event;
- determined to be outside the user’s scope; or
- subjected to targeted exact-title and identifier searches that found no supporting record.

Execution of a proposed order does not satisfy judicial filing or entry. Filing does not establish service. A party’s later description of an order does not replace the directly available order when the record identifies or supplies it.

Do not serialize while a referenced material document remains unresolved.

## `TimelineDraft` readiness check

Before serialization, confirm:

1. `originalRequest` can be copied exactly.
2. `timeRange` can be derived from supported and comparable entry dates without adding precision.
3. `summary` can orient the reader without replacing atomic entries.
4. Relevant records produce a non-empty `entries` list.
5. Every entry can be represented with only `dateRange`, `eventType`, `summary`, and non-empty `citationKeys`.
6. No internal candidates, fingerprints, relationship edges, gap objects, confidence values, or reconciliation metadata will leak into the response.

## Corrective action

Fix supported omissions, over-aggregation, provenance errors, or schema defects before serialization. Do not repair incompleteness by inventing an event, date, source, or relationship.

If a material limitation cannot be resolved, state it cautiously in the top-level `summary` without creating an unsupported entry.

