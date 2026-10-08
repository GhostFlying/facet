# Existing deployment: current-label upgrade and bounded live verification

2026-10-08. User explicitly requested upgrading the existing real deployment
and verification. Accepted source/main: `e165ac54baa31827ce129466fbaf7122e8f90b8b`;
PR #106 independently reviewed, Python 3.12/3.13 full CI and dual-architecture
build passed. Published index:
`sha256:f3c96cbc98eae710fa1ac81b60a7d0ec6303d1e180789f135f7d89d5089c07aa`.
Anonymous pull, all packaged source bytes and non-root UID were verified.

## Bounded operation

Preserve the existing Compose project, local proxy/loopback overrides, volume,
accounts, configured labels and selected historical window. Sync is stopped.
Reuse the existing private operator's writer-locked SQLite backup API, config,
credential and cleanup-journal backup; verify integrity/private permissions.
Freeze a private before snapshot and actual eight historical label-attention
event/job pairs. Save a durable submitted marker before exactly one production
CLI `run --once`; missing operator response never causes automatic resubmission.
No wrapper performs business SQL updates or Gmail mutations.

Select the verified immutable image in the private deployment environment and
recreate Compose without starting an indefinite daemon. The accepted runtime
owns backed-up v3-to-v4 migration and current-label learning/notification
completion. Run once through the image and existing deployment-only proxy.
No whole-command kill timeout while insert may have been dispatched.

## Acceptance and stop gates

Compare before/after durable snapshots: all prior mappings preserved; binding
account/role/lineage invariants (not legitimate refresh/probe timestamps),
configuration, action-label mapping and historical scope/discovery unchanged;
prior stopped threads not revived; no new attempt for the protected unknown's
source message. New attempts, if any, must have confirmed verified mappings.
Unknown checks may update their count/deadline but cannot fabricate ownership.
Report exact old label-event completions, remaining categorized attention,
current activation receipts/rule changes, new mappings and typed warnings.
Repeat only offline inspection after the cycle; do not submit another sync cycle
without first interpreting its result. Take a post-run writer-locked backup.

Stop on writer conflict, account/scope/config mismatch, unmanaged target,
persistence/auth failure, new unknown or unexpected protected-state change.
Keep changed durable state after any target write; never restore a pre-insert DB.
Schema v4 is not readable by the old image: rollback is stopped maintenance,
not selecting the old image against v4 or blindly restoring a stale backup.
No new backfill epoch, operator-selected rule/historical-window expansion, source mutation, target cleanup,
unknown resend, perpetual service, OAuth scope expansion or Release is authorized.
