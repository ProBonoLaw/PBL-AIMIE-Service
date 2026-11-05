# Atomic Event Examples

Use these examples as decision patterns, not as case facts or fixed event-type vocabularies.

## Complaint through termination

Source passage:

> After Smith complained on March 3, HR interviewed Jones on March 5, sent its findings to Anderson on March 7, and Jones was terminated on March 10.

Extract four candidates:

1. Smith submitted a complaint on March 3.
2. HR interviewed Jones on March 5.
3. HR sent findings to Anderson on March 7.
4. Jones was terminated on March 10.

Do not collapse these into `Smith complained, resulting in Jones's termination.` That loses intermediate acts and overstates causation unless a source expressly supports it.

## Document lifecycle

Source passage:

> The motion was filed on May 1, served on May 2, opposed on May 15, and denied on June 4.

Extract four candidates. Filing, service, opposition, and disposition have different procedural functions even though they concern one motion.

## Communication and later conduct

Source passage:

> Lee emailed the safety instructions to Patel on July 6. Patel acknowledged the email that afternoon and changed the operating procedure on July 8.

Extract three candidates: sending, acknowledgment, and procedure change. Do not assume the email caused the change unless the evidence supports that relationship.

## Witness account of an earlier occurrence

Source passage:

> At her August 20 deposition, Rivera testified that she saw the gate unlocked on August 4.

Potentially extract:

1. Rivera testified on August 20 that she observed the gate unlocked.
2. Rivera allegedly observed the gate unlocked on August 4, characterized as testimony rather than independently established fact.

Whether both candidates are material depends on the requested scope. Do not assign the deposition date to the underlying observation.

## Discovery within a search

Source passage:

> Officers stopped the car, searched the trunk, found a laptop, seized it, and arrested Brown.

Extract separate candidates for the stop, search, discovery, seizure, and arrest when each is supported. These actions have different legal and causal roles.

## Medical sequence

Source passage:

> The patient reported chest pain, was examined by Dr. Chen, received an ECG, and was discharged with instructions to follow up.

Normally extract separate candidates for the reported symptom, examination, diagnostic procedure, and discharge. Extract a distinct follow-up instruction or communication when it is material and independently supported.

## Continuous state versus repeated events

Source passage:

> The server remained offline from September 1 through September 3.

One range-based state candidate is appropriate if the source describes uninterrupted downtime.

Source passage:

> The server failed on September 1, restarted on September 2, and failed again on September 3.

Extract three candidates. A September 1–3 range would erase distinct state changes.

## Possible duplicate assertions

Record A says:

> Wilson called dispatch at 9:12 p.m.

Record B says:

> Dispatch received Wilson's call shortly after 9:10 p.m.

At candidate extraction, preserve both assertions if event identity is not certain and mark them as possible duplicates. Let downstream identity resolution determine whether they describe the same call and whether the times conflict or merely differ in precision.

## Negative events and omissions

Source passage:

> The policy required a supervisor review within 24 hours. The audit found no supervisor review in the following seven days.

A failure-to-review candidate may be appropriate because both the expected action and supported nonoccurrence are present.

Source passage:

> The file contains no supervisor review.

Do not automatically extract `No review occurred.` Absence from the returned file may reflect incomplete records rather than a supported historical event.

## Same date does not mean same event

Source passage:

> On October 12, Kim approved the refund, accounting issued it, and the customer confirmed receipt.

Extract approval, issuance, and confirmation separately despite the shared date.

## One event with descriptive detail

Source passage:

> At 2:15 p.m., Davis signed the revised settlement agreement in counsel's office while represented by Morgan.

This is normally one signing event. The time, location, document version, and counsel's presence describe the same primary act rather than separate occurrences.
