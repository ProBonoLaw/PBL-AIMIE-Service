---
name: timeline-materiality-review
description: Review reconciled atomic events for materiality against a user's requested legal or investigative timeline scope. Use after evidence reconciliation and before completeness review when deciding which supported events belong in a major-events, incident, procedural, discovery, safety, agency, or other scoped timeline; do not use to extract, merge, reconcile, or serialize events.
---

# Timeline Materiality Review

Select the supported atomic events that answer the user's actual timeline request. Optimize for maximum recall of materially relevant events, not the largest event count and not the shortest narrative.

## Stage boundary

Work from the identity-resolved, relationship-analyzed, gap-reviewed, and evidence-reconciled atomic event set. Use the exact `originalRequest` as the governing scope.

Materiality review decides retention only. It does not:

- determine truth, credibility, admissibility, liability, or legal effect;
- merge, split, deduplicate, reconcile, or redraft evidence;
- infer an event, relationship, issue, or procedural stage;
- rank evidence by source type, source count, author, or perceived authority; or
- serialize the final `TimelineDraft`.

If a proposed event is not atomic, contains an unsupported relationship, or has an unresolved identity or evidence conflict, return it to the appropriate earlier stage instead of repairing it here.

## Materiality standard

Retain an event when it has a supported nexus to the requested scope and materially changes, establishes, documents, contests, explains, or resolves at least one significant case state, including:

- procedural posture or the lifecycle of a material issue;
- custody, parenting time, placement, decision-making authority, or relocation;
- legal rights, duties, restrictions, remedies, or financial obligations;
- a material allegation, denial, finding, recommendation, or evidentiary position;
- discovery availability, testimony, production, or a material discovery dispute;
- CPS, child-welfare, medical, psychiatric, safety, or law-enforcement involvement or disposition;
- investigation, evaluation, arbitration, adjudication, enforcement, or contempt;
- compliance, noncompliance, interruption, escalation, or a consequential state change; or
- a necessary intermediate event without which a retained sequence would be materially misleading or unintelligible.

Materiality is request-relative. An ordinary visitation occurrence may be immaterial to a major-events timeline but material to a parenting-time-compliance timeline. A small financial ruling may belong in a comprehensive procedural history but not in a timeline limited to custody and safety incidents.

Do not use a fixed event quota, a numerical score, or event type alone as the decision rule. A filing, hearing, communication, medical visit, or agency contact can be material or routine depending on what it changed, documented, disputed, or resolved.

## Scope calibration

1. Parse the request for express subjects, event categories, parties, issues, date bounds, and requested level of detail.
2. Treat expressly requested categories as strong inclusion signals. Do not omit a supported hearing, discovery event, emergency, CPS event, or other named category merely because another issue appears more important.
3. For requests using `major`, `noteworthy`, `key`, or similar language, apply the materiality standard and exclude ordinary implementation activity that adds no significant case-state information.
4. For `complete`, `all`, compliance-history, communication-history, treatment-history, or similarly exhaustive requests, lower the retention threshold within that stated scope without abandoning relevance or atomicity.
5. Honor date, party, issue, and proceeding limits exactly. Do not broaden into unrelated case history merely because it is available.
6. When the scope is genuinely ambiguous, use the narrowest reasonable interpretation that still covers every category the user expressly named. Preserve a material limitation for the top-level summary when necessary.

Treat the earliest supported initiation and latest supported disposition of each material issue as presumptively material. Exclude either only when it is outside the user's scope, duplicates the same resolved occurrence, or lacks direct support.

## Retention review

For each reconciled atomic event, determine:

1. **Scope nexus:** Does the event directly concern the requested subject, category, period, party, or issue?
2. **Significance:** Does it change or document a significant state, initiate or resolve a material issue, mark an escalation or interruption, preserve a material conflict, or supply a necessary intermediate step?
3. **Incremental value:** Does it add distinct event-level information rather than repeat an already represented occurrence or merely restate background?
4. **Evidence discipline:** Can it remain accurately characterized with its supplied date precision and direct citation keys, without an inference of importance, causation, or legal effect?

Retain the event when all four are satisfied. If missing context could materially change the decision and the retrieved evidence provides a concrete lead, route that lead to gap analysis for a narrow search, then reprocess any new evidence through the upstream stages before repeating materiality review.

## Events ordinarily retained

When within scope and supported, ordinarily retain:

- pleadings or requests that initiate a material issue;
- hearings at which a material argument, testimony, ruling, or state change occurred;
- substantive temporary, interim, arbitral, or final decisions and their distinct implementation acts when material;
- emergency medical encounters, safety incidents, police responses, and CPS contacts or dispositions;
- depositions, evaluations, material productions, and discovery refusals or disputes;
- material recommendations, findings, allegations, denials, corrections, and competing accounts;
- relocation, custody, parenting, support, enforcement, and contempt events that change or contest operative conditions; and
- significant initiation, intermediate disposition, and final disposition events for each material issue.

These are presumptions, not automatic inclusions. Preserve each as a separate atomic event when it independently meets the standard.

## Events ordinarily excluded

For a major-events timeline, ordinarily exclude:

- routine scheduling, confirmations, reminders, and administrative coordination;
- docket or signature mechanics that neither change nor explain procedural posture;
- ordinary successful visitation, treatment, or compliance occurrences;
- repetitive communications that add no new action, position, consequence, or state change;
- background facts that do not assert a material occurrence within scope;
- evidence duplicated by the same resolved occurrence; and
- implementation details with no independent significance.

Retain an otherwise routine event when it evidences a material breach, denial, conflict, escalation, interruption, pattern boundary, change in position, or necessary link to a later material event. Do not exclude an event merely because it appears mundane in isolation.

Do not exclude the first supported initiation or latest supported disposition of a material issue merely because other entries already describe that issue.

Before retaining an administrative implementation event, confirm that it independently changes legal or operative status. Execution, electronic-signature completion, filing, and service are not automatically material.

## Repeated and aggregate occurrences

- Retain each repeated occurrence that independently meets the materiality standard, even when the occurrences share a date range, institution, participant, or event type.
- Do not compress separately supported visits, calls, reports, hearings, filings, or other point events into one period entry.
- Do not retain every routine occurrence solely because a pattern might exist. Retain those that independently change or document a material state, or that fall within an expressly exhaustive request.
- A source-supported finding or report about a pattern may itself be a material atomic reporting, evaluation, or decision event. Do not transform it into proof of each underlying occurrence.
- When a record says `four emergency visits`, `multiple CPS reports`, or similar without resolving the underlying occurrences, flag an aggregate-occurrence gap. Do not manufacture individual events or treat the plural occurrences as one atomic event. If unresolved, retain only a separately supported atomic reporting or finding event when material, and preserve the evidentiary limitation for downstream review.

## Allegations, conflicts, and evidence strength

Materiality and proof are separate questions. A disputed allegation, denial, recommendation, or minority account can be material even when it is not an established fact. Retain its source-grounded attribution when it materially affected the case, frames a live dispute, or is necessary to understand a later material action.

Do not retain repetitive versions of the same allegation merely to increase source count. Do not exclude a material account because it conflicts with a ruling or a more authoritative-looking source. Evidence reconciliation governs how the account is represented.

## Internal audit and handoff

Maintain an internal exclusion ledger containing enough information to revisit each decision: the event or fingerprint, retain/exclude decision, scope issue, and concise reason. Do not emit this ledger or add materiality fields to `TimelineDraft`.

Before handoff:

1. Confirm every category expressly requested by the user has proportionate representation when supported.
2. Confirm every retained event is atomic and every excluded event has a scope- or significance-based reason.
3. Reconsider any exclusion whose absence would hide a material initiation, change, conflict, intermediate step, or final disposition.
4. Confirm routine repetition has not crowded out a more significant event in the same issue lifecycle.
5. Confirm no event was retained merely because it was recent, detailed, highly cited, or easy to narrate.
6. Pass the retained atomic event set and internal exclusion ledger to completeness review.

Do not change `dateRange`, `eventType`, `summary`, or `citationKeys` merely to make an event appear more or less important. Final output still contains only the fields allowed by the caller's timeline contract.

Read [references/materiality-examples.md](references/materiality-examples.md) when the inclusion boundary is uncertain, repeated events create pressure to aggregate, or a major-events request competes with a more exhaustive evidentiary record.

Read [references/criminal-case-materiality.md](references/criminal-case-materiality.md) for criminal investigations or prosecutions, including assaultive conduct, unlawful-entry or property offenses, financial or white-collar matters, multi-defendant cases, criminal discovery, suppression issues, plea or trial proceedings, sentencing, restitution, forfeiture, and appeal.
