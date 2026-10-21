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

Implementation review and the exact candidate SHA will be recorded after review.

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
