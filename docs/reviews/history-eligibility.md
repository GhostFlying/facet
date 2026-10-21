# History eligibility review evidence

## Plan

- Base: `f7e804cc02b029205577b9b85090867caf166dcc`.
- Plan: `docs/implementation-plans/history-eligibility.md`, SHA-256
  `aca1230b294fdcd33cd540fac06660384fb08c26871af9b4686188ce045ceeb0`.
- Independent reviewer: `eligibility_plan_review`, GPT-6.1 Sol xhigh, 2026-10-21.
- Verdict: approved. Reviewer authored neither plan nor implementation.
- Required constraints: strict identity/date/label validation before exclusion;
  exact one-of candidate result; malformed eligible From uses invalid_input,
  invalid metadata uses consistency_failure. Provider codes stay typed.
- Legacy repair requires positive current exclusion with no tracked/admitted
  thread, message-or-thread mapping/insert/projection effect, claim, action
  command or current receipt. Recheck revisions and effects after source read,
  atomically record the original request_conflict in the completion audit.
  Label-absence observations are not business effects.
- Source-only reconcile retains its existing coverage policy for missing
  History notifications; no History scan or absence-as-exclusion inference.

## Retry deadline correction

The independent implementation reviewer `eligibility_implementation_review`
(GPT-6.1 Sol xhigh) requested changes on `4629f29`: legacy exclusion rechecks
discarded provider Retry-After and could repeat immediately. A synthetic
two-call reproduction confirmed the issue; the review's 145 focused tests
otherwise passed. This candidate is not accepted for live operation.

The original plan reviewer independently approved the narrow plan delta,
SHA-256 `9be301d92b34c500069df0482f01cddc4ecd84640724814abb7ccf9f4273ba4a`.
Use existing next_attempt_at while retaining attention/request_conflict, defer
the entire unprotected legacy cohort beyond the selection limit, preserve
longer deadlines, and stop the pass. Only metadata rechecks use this backoff;
existing-effect and label convergence remain available without network reads.
Restart, expiry, fallback delay and protected-work tests cover this correction.

## Final implementation acceptance

Independent reviewer `eligibility_implementation_review` approved exact candidate
`b55957a4c715066d55eb865617b3855aff5ddc01` against revised plan digest
`9be301d92b34c500069df0482f01cddc4ecd84640724814abb7ccf9f4273ba4a`.
The reviewer authored neither plan nor implementation. Independent focused
verification passed 147 tests in 18.51 seconds. The original throttling fault
injection now performs one provider read across two immediate convergence
passes, preserving the durable deadline and original attention facts.
No further actionable finding remained in the reviewed scope.

Root focused verification passed 161 tests. The local full suite passed 3059
tests in 887.97 seconds, but began before the final retry correction; it is not
the exact final candidate gate. Exact candidate CI and merged-main CI both
passed 3061 tests plus 48 CLI smoke checks on each of Python 3.12 and 3.13.
Lint/format/safety/locked dependencies and amd64/arm64 image builds passed.

- [Candidate offline CI](https://github.com/GhostFlying/facet/actions/runs/39541316702)
- [Candidate image build](https://github.com/GhostFlying/facet/actions/runs/39541316704)
- [Merged-main offline CI](https://github.com/GhostFlying/facet/actions/runs/39542656518)
- [Official image publication](https://github.com/GhostFlying/facet/actions/runs/39542656531)

PR #126 merged as `99fa3238bed2d512867da153f250bea078241267`; its production and
test tree matches the reviewed candidate. Authorized live source-only
maintenance and actual deployment results are recorded in development-status,
separately from this implementation acceptance.

## Operational receipt review

Independent reviewer `eligibility_plan_review` approved the deployment/source
coverage receipt at base `99fa3238bed2d512867da153f250bea078241267`. Reviewed
development-status SHA-256 was
`c54333a61750050783152f4859a8608d8b1d5b598865098c8fc6c939918554a4`;
review-evidence SHA-256 was
`f250869d87ece746757627925e59d842217dedef4663d3088501f23998e60fc7`.
Read-only review verified private saved operational proof against the documented
4897-message coverage, two guarded closures, 219 warning audits, original-error
legacy audit, elapsed/retry statistics and unchanged protected business state.
No private mail/account/request identifiers appeared in the receipt. External CI
and publication were assessed from supplied operational evidence.

The final resumed-cycle paragraph was subsequently verified by root against live
Dashboard snapshots and Docker at 13:05:30 +08:00: healthy, fresh, queue empty,
no active issues, 5033 confirmed messages, official commit and zero restarts.
HTTPS Dashboard and status both returned 200. This later live health verification
is separate from the independent receipt review above.
