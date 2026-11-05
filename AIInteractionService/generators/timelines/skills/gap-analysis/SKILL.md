---
name: gap-analysis
description: Find missing intermediate events, referenced records, and unexplained transitions in a legal timeline. Use after relationship analysis when case-search tools can retrieve additional supporting records.
---

# Timeline Gap Analysis

Inspect the event graph for missing supported steps that materially affect reconstruction of the case. A gap is a search target or limitation, not permission to create an event.

## Gap types

Look for:

- unexplained transitions between documented events;
- references to a communication, meeting, order, filing, report, interview, decision, or incident not yet represented;
- an action that expressly depends on an earlier request, authorization, notice, finding, or recommendation;
- a response whose initiating event is absent;
- a stated consequence whose intervening implementation is absent;
- date jumps, participant changes, or state transitions that suggest a referenced intermediate event;
- missing records necessary to understand a conflict, amendment, denial, correction, or procedural outcome.

Distinguish an unresolved evidentiary gap from an affirmative omission. Absence from search results does not prove that an act did not occur.

## Critical-scope coverage

For every critical umbrella concept in the original request, maintain an
internal coverage record identifying the required retrieval clusters, clusters
searched, searches that returned records, clusters with no supporting records,
and any clusters left unsearched because the search budget was exhausted.

Do not mark search closure complete while a required cluster remains
unsearched. If the budget is exhausted first, retain only source-grounded
events and describe the incomplete scope coverage as a limitation in the
top-level summary. Never represent incomplete coverage, a model refusal, a
content filter, or a parser failure as evidence that no responsive event
occurred.

## Procedure

1. Review each supported relationship and adjacent pair of material events.
2. Extract concrete leads: people and aliases, dates, document names, quoted phrases, locations, case numbers, transaction identifiers, and event types.
3. Use `search_case_events` first for the suspected occurrence.
4. Use `search_case_context` for explanatory records or referenced material when event search is insufficient.
5. Add newly supported occurrences as atomic candidates, then return them through identity resolution and relationship analysis.
6. Record material unresolved gaps internally with the searches attempted and why the gap matters.
7. Stop when additional targeted searches no longer reveal materially distinct supported events or relationship evidence within the requested scope.

Search iteratively but proportionately. Do not broaden into unrelated case history merely because it is available.

A search result may resolve or clarify an internal lifecycle gap without qualifying as a material timeline event.

Do not route a newly located scheduling, service, signature, certification, transmission, docket, or other administrative act into the retained timeline merely because it helped establish document or issue status.

Apply candidate extraction and materiality review normally. A nonmaterial result may close an internal ledger item without entering `TimelineDraft.entries`.

## Aggregate-occurrence gaps

Treat an aggregate statement that explicitly refers to multiple underlying occurrences as a decomposition gap when those occurrences are material to the requested timeline.

Examples include:

* four emergency-department visits;
* three police contacts;
* multiple CPS reports;
* several hearings;
* two later filings;
* repeated supervised visits.

Do not manufacture separate events from the count alone. Instead, search for records identifying the individual occurrences by date, actor, location, report number, or other supported detail.

If targeted searches identify the individual occurrences, route each through candidate extraction and atomic decomposition.

If the indexed evidence supports only the aggregate fact and the aggregate fact is itself material, preserve it as an attributed aggregate statement rather than inventing individual events.

## Prohibited gap filling

- Do not create a placeholder timeline entry for an event that lacks direct support.
- Do not infer a routine procedural step occurred merely because it normally would.
- Do not assign a date based on surrounding events.
- Do not convert a failed search into proof of nonoccurrence.
- Do not bridge a sequence with an invented causal explanation.

## Issue-lifecycle coverage

Maintain an internal ledger of each material case issue discovered in the evidence, such as:

* dissolution;
* custody or parenting-plan modification;
* relocation;
* child support;
* spousal maintenance;
* contempt or enforcement;
* discovery;
* GAL investigation;
* psychological evaluation;
* CPS/child-welfare investigation;
* medical or psychiatric crisis;
* arbitration.

For each material issue, determine which lifecycle stages are supported or referenced:

initiation → interim action → investigation/discovery → hearing/adjudication → decision → reconsideration/appeal → implementation/final disposition

Not every issue requires every stage. Do not infer that a missing stage occurred.

However, when retrieved evidence establishes that an issue remained pending, was referred for later determination, was arbitrated, or required later court implementation, treat the absence of its apparent disposition as a gap-search target.

Search for the missing disposition before declaring search closure.

### Issue-lifecycle ledger

Maintain an internal ledger of each material issue and its supported lifecycle events. Use referenced but unrepresented initiations, intermediate decisions, implementations, and dispositions as targeted gap-search subjects.

Do not infer that a customary lifecycle stage occurred. Record only supported stages and concrete references to potentially missing stages.

### Referenced-document gaps

Treat an expressly referenced document, order, report, disposition, or implementing instrument as a distinct gap target when it is material and not represented.

Examples include:

- a decision directing counsel to prepare conforming final orders;
- a proposed order awaiting judicial entry;
- an investigation referencing a later closure or disposition;
- a temporary ruling reserving final determination;
- an order referencing an amended or superseding order; and
- a motion identified as producing a later ruling.

Search first using the exact supplied document title, report number, intake number, motion title, case number, issuing body, and quoted phrases. Use broader issue searches only when exact-identifier searches are insufficient.

Do not treat preparation, execution, signature, submission, filing, entry, service, or enforcement as interchangeable lifecycle stages.

## Handoff to `TimelineDraft`

Only supported events enter `TimelineDraft.entries`, and each must have a non-empty `citationKeys` list. When an unresolved gap materially limits interpretation, describe the limitation cautiously in the top-level `summary`, for example: `The returned records do not identify the decision made between the investigation and the later enforcement action.`

Do not add gap objects, synthetic entries, or empty citation arrays to the response.

## Search termination

Maintain an internal ledger of targeted searches, including the query,
the gap being investigated, and whether the search revealed:

- a materially distinct event;
- new relationship evidence;
- a useful unresolved reference; or
- no relevant new evidence.

Stop investigating a gap when:

1. two consecutive targeted searches reveal no materially distinct event
   or relationship evidence;
2. the available leads have already been searched;
3. another query would be substantially equivalent to a completed query; or
4. the remaining gap cannot be resolved from the indexed records.

A search that only returns previously reviewed records does not reset the
no-new-evidence count.

After stopping, preserve any material unresolved limitation for the
top-level timeline summary. Do not create a placeholder event or infer
the missing step.

A newly located administrative lifecycle record does not reset the no-new-material-evidence count unless it supports a materially distinct event.

Do not recursively investigate the lifecycle of a document located solely to close another gap unless the new document expressly identifies another potentially material unresolved event.