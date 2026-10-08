# Current label observations review

Base: `618887a070a19738618c3a7602df4d570b4a35be`. User-approved semantics:
2026-10-08; engineering only, no live Gmail or deployment authority added.

Independent Sol xhigh plan review accepted SHA256
`949b939f942d25eca456131b66fff19b246fe5576c84e0e0cc7d62d2926b0e48`.
The bounded corrections were independent activation identity rather than legacy
History keys, H0 before resumable initial baseline, and legacy acknowledgements
only for proven executed matching category/label. Empty provider label lookup
remains a consumer/no-op; presence precedes sender parsing; stopped threads and
BlackList precedence stay protected. No generic capability framework is added.

## Candidate acceptance

Independent reviewer `current_labels_plan_review` accepted source candidate
`7e97b21986db07c02e93b6cf5203a7a8b9e15fdb`. The initial implementation finding
was a missing durable retry deadline when a historical label attention recheck
failed at the provider. The bounded fix uses existing `jobs.defer_job`, preserves
the event and unknown/stopped guards, and does not acknowledge an unobserved
label state. A regression proves a 3600-second deadline, exclusion from immediate
scheduling and safe no-tag completion after the deadline. Nineteen affected
current-action and runtime cases passed independently; unaffected earlier
conclusions remain valid. The reviewer also independently exercised interrupted
two-page initialization baseline resume without rules or activation receipts.

Root focused checks cover real CLI initialization/OAuth binding, current label
learning, insert/readback/mapping, sticky-tag restart and observed reactivation;
atomic rollback, legacy acknowledgement, backed-up migration and stopped guards
are separate synthetic checks. The earlier full run on the initial candidate
finished with 2894 passes and four failures: fixtures lacked their owner's bound
configuration artifact and referenced the replaced runtime composition class.
The fixtures were corrected without weakening production checks; all ten affected
runtime cases passed. That original full run remains failed evidence, not a
green final-candidate gate. Locked dependencies, Ruff lint/format, both CLI help
smoke checks, diff checks and repository safety passed on the accepted source.

## Exact production image

Image `facet:7e97b21` has revision label matching the accepted source and image ID
`sha256:d7a0510e2b5acd1ca99cdee45c9134bce9bb307df8b592072d11ffd8f8fd9e66`.
The repository Dockerfile was built from a Git archive on the previously
authorized build host after a local Docker Hub timeout, then loaded locally.
Qualification ran as UID/GID 10001, with a read-only root filesystem, networking
disabled, private tmpfs and read-only mounted synthetic tests/test dependencies.
No host application source was overlaid: the tests' checkout seam links to the
image's own `/app/src`. All 55 selected production CLI, current-action, migration,
runtime and learned-rule backfill/gap cases passed in 284.80 seconds. This includes
complete sync, unknown-without-resend and restart continuation through the CLI;
fake transport replaces only external OAuth/Gmail.

Final exact-head PR full checks/CI remain pending merge gates. Existing live
records, accounts, labels, mappings, unknown and deployment were not changed by
this engineering unit.
