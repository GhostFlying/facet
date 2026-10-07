# History incremental admission repair

Plan: `docs/implementation-plans/history-incremental-admission.md`, SHA256
`8fc273e0b5a8b117e8f02d8e36b6ac0933520de1a0ae3b57ef0ef37c6b4b2a22`.
Independent plan review: `/root/history_admission_plan_review`, Sol 6.1 xhigh,
APPROVE against base `40cbb49733e88ae903a6d90b67f1eebf6a1ad16a`.

Implementation candidate: `a3cd969e6529336fe60676dc8d8887e39a06e553`.
Independent implementation review: `/root/history_admission_impl_review`,
Sol 6.1 xhigh, APPROVE on the exact corrected candidate. Reviewer independently
passed 117 affected/adjacent cases and reproduced the corrected 120-second
Retry-After deadline with one metadata call through the 2-second follow-up.

## Product evidence

The real CLI subprocess path completed synthetic init, authorization/binding,
empty preview, explicit start and an empty first cycle. A subsequent production
CLI command installed a sender rule without changing the sealed initial epoch.
A checkpoint-origin History arrival then admitted a new thread via `future_rule`,
copied its two available non-draft messages, verified readback and persisted
mappings. A fresh process consumed another History record for the confirmed
message without metadata reads or another insert. The fake replaced external
Gmail transport only; readiness, bindings, rules and epochs were not DB-seeded.
Synthetic body/header sentinels were absent from command output and state files.

Focused source/repository/History/CLI checks passed on the initial candidate;
the independent reviewer found a real 429 scheduling defect: Retry-After was
lost and replaced by a fixed one-second delay. The corrected candidate passes
31 affected cases including a durable 120-second deadline and no early retry.
Existing successful review conclusions were retained for unchanged code.
The obsolete full run was interrupted after the correction became necessary;
it is not full-suite evidence. The final corrected candidate passed the complete
offline suite: 2725 tests in 533.79 seconds. Locked environment sync, repository
Ruff/format, spike CLI help, diff checks and staged/tracked safety checks passed.

The unchanged pinned Dockerfile built on sgbox and the exact image was imported
locally as `facet:a3cd969`, image ID
`sha256:5d66aa533abba564c31b8cf6c57bfc3d2446ffc51eaeffa877a5189873276bc4`.
Image provenance is the corrected candidate SHA and its runtime user is
`10001:10001`. With networking disabled and a separate synthetic volume, this
image passed the same actual CLI subprocess full-thread admission/readback,
restart deduplication and production-state/output privacy assertions. Only the
external fake transport/test driver was mounted; app source was not overlaid,
and the real state volume was not mounted. Full CI/merge/publication and any
live-service upgrade remain unclaimed.

Remaining error-diagnostic follow-up: source metadata 404 currently reaches
generic attention via the provider's `invalid_input` classification rather
than the dedicated `source_missing` event/job category. It does not admit or
insert the missing message, and work remains durable. Normalize this endpoint
failure in the next bounded provider/error-path unit; this acceptance does not
claim the complete Phase 1 source-loss/recovery gate.

No real Gmail operation, deployment, service resume, scope change, deletion,
attention override or retry of the existing unknown insert occurred.
This is a bounded engineering correction, not M1-M6 or live acceptance.

## Separate HTTP replay investigation

Primary upstream evidence was checked on 2026-10-07:

- [httplib2 issue 258](https://github.com/httplib2/httplib2/issues/258) reports
  non-idempotent POST/PATCH resends after the server read the request but dropped
  the response, including with `RETRIES=1` on the locked 0.32.0 release.
- [Proposed fix 259](https://github.com/httplib2/httplib2/pull/259) restricts
  resends after dispatch to idempotent methods and separately handles stale idle
  connections. It was open/unmerged with no submitted reviews at the check;
  this is not an accepted release or proof that an upgrade fixes Facet.
- [Issue 181](https://github.com/httplib2/httplib2/issues/181) also documents
  that global RETRIES counts attempts, so zero can prevent the first dispatch.
  Neither that knob nor Google `num_retries=0` proves one wire attempt.
- [urllib3 retry documentation](https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html#urllib3.util.Retry)
  distinguishes pre-send connection failures from post-send read failures;
  default retry methods exclude POST. Explicit retry disabling is supported.
  [Requests HTTPAdapter](https://docs.python-requests.org/en/stable/api/#requests.adapters.HTTPAdapter)
  provides a mature transport with explicit retry configuration.

Recommendation for the next bounded transport unit: retain Google request
construction but use a thin access-only Requests transport with retries and
redirects explicitly disabled, following the cleanup transport already wire
tested in this repository. Do not copy httplib2 internals, pin an unmerged PR,
or introduce another automatic credential-refresh/replay layer. Verify the
actual Google insert request against a local server that accepts its body and
drops the response: exactly one received POST, durable unknown outcome, and
zero further POSTs after restart. Also cover 401/429/5xx and redirects.
This recommendation is not implemented by the History candidate; the normal
sync factory still has its known wire-replay risk. Application recovery remains
mandatory regardless of HTTP library choice.
