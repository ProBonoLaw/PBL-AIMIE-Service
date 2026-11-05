---
name: relationship-analysis
description: Analyze source-supported temporal, procedural, responsive, and causal relationships between resolved legal-timeline events. Use after event identity resolution and before gap analysis or serialization.
---

# Timeline Relationship Analysis

Build a conceptual event graph from the resolved atomic events. Events are nodes; supported relationships are edges. Use the graph to explain the sequence without turning chronology into causation.

## Boundaries

- Use only the returned case records and their directly supported event assertions.
- Preserve atomic events; a relationship does not authorize merging its endpoints.
- Do not add a `relationships` field because `TimelineDraft` does not define one.
- Do not infer motive, knowledge, authorization, reliance, or causation merely to make the timeline coherent.

## Relationship classes

Evaluate relationships such as:

- temporal: preceded, followed, overlapped, or occurred during;
- procedural: requested, authorized, implemented, amended, superseded, or enforced;
- responsive: acknowledged, answered, disputed, corrected, appealed, or investigated;
- evidentiary: corroborated, contradicted, reported, or memorialized;
- causal: caused, triggered, prompted, enabled, prevented, or resulted in.

Chronological order is represented by event dates and normally needs no relationship assertion. Record a substantive relationship only when it improves understanding and the source supports it.

## Evidence standard

Classify a possible relationship internally:

- `explicit`: a source directly states the relationship;
- `attributed`: a party, witness, pleading, or report alleges the relationship;
- `supported inference`: record facts materially support the relationship even though no source states it directly;
- `temporal only`: one event preceded another without evidence of a substantive link;
- `unsupported`: the proposed relationship rests on speculation.

Use `supported inference` only when the governing prompt permits inference. Label it as an inference and state its basis. Never promote an attributed relationship to established fact.

## Procedure

1. For each material event, examine supported predecessors and successors.
2. Search the returned evidence for express connective language such as `because`, `after receiving`, `pursuant to`, `in response to`, `based on`, `authorized`, `therefore`, or `resulted in`.
3. Identify the precise source passage supporting both endpoints and the relationship.
4. Preserve intermediate events rather than drawing a long edge across a documented multi-step process.
5. Record conflicting explanations as competing attributed relationships; do not choose a winner without an evidentiary basis.
6. Send missing intermediate steps or unexplained references to gap analysis.

## Handoff to `TimelineDraft`

Retain the graph internally. Because `TimelineEntryDraft` has no relationship field, express only material, source-supported relationships in an entry summary or the top-level timeline summary.

When a summary states a relationship, include in that entry's `citationKeys` every returned citation directly supporting the occurrence and the stated relationship. If the schema cannot preserve the relationship without overstating it, keep the entries separate and rely on chronological order.

