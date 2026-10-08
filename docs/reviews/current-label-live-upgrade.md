# Existing deployment: current-label live verification

2026-10-08. User explicitly authorized upgrading the existing real deployment
and verification. No account, selected historical window, OAuth scope, configured
label, source mutation, target cleanup or unknown resend was added.

## Procedure and artifact

Independent Sol xhigh approved the operational plan SHA256
`a716dce9542f09188a82280e42fb43b5dc46768548a518dce161de81d3b4a095`
and private operator SHA256
`14bfa14ab383075562c890e23cdbb1f431889dd7a59801f0a6f9b5020fea833a`.
Synthetic review verified JSON round-trip, protected-state rejection, marker before
one CLI dispatch, rejection of resubmission and receipt-backed learning. The
operator reuses the accepted writer-locked backup and snapshot/CLI helpers;
its business queries are read-only. It does not update business rows or call
custom Gmail mutations. Binding lineage comparison includes binding revision,
without rejecting ordinary credential-refresh metadata changes.

Installed full-commit image:
`ghcr.io/ghostflying/facet:e165ac54baa31827ce129466fbaf7122e8f90b8b`.
Published amd64/arm64 index:
`sha256:f3c96cbc98eae710fa1ac81b60a7d0ec6303d1e180789f135f7d89d5089c07aa`.
Imported amd64 image:
`sha256:3b19a113373dcf4256808ccd6499772f200406530187a7cb0fded0490445a30f`.
PR/main checks and publication passed. Anonymous pull, both platform manifests
and attestation manifests, UID/GID 10001 and all 114 packaged source files matched
byte for byte were verified. Compose retained its volume, loopback exposure and deployment-only
proxy; the only private environment change was the selected image.

## Actual result

Stopped, writer-locked pre/post SQLite-backup-API bundles include WAL-visible
state, configuration, credentials and cleanup journal. Integrity checks and private
permissions passed. A durable private marker preceded exactly one actual image
CLI `run --once`; no overall insert-killing timeout or automatic resubmission.

The cycle took 68.49 seconds: one History page, 28 resolved events and 12 verified
projections, with zero new attention and no warnings. Mappings rose 4309 to 4321;
all prior mappings were preserved. Every new attempt has its verified mapping.
All eight frozen old label-attention event/job pairs reached consumed/completed
through the normal current-state consumer; attention fell 11 to 3. Schema became
v4 through the backed-up production migration. No business SQL correction was
used. Account/binding lineage, config, rules, configured labels, historical scope/
discovery and prior stopped generations passed preservation checks.

No new activation receipt or rule effect occurred; this verifies current-state
no-op/event convergence, not a new live AddDomain learning or remove/re-add test.
The old unknown retains identity/attribution, no new unknown was created and its
source message was not reinserted. Its three dependent projection attention jobs
remain. Final queue has no queued jobs, one blocked job and one recovery retry-wait.

Fresh read-only target enumeration found 4321 mapped items, two permitted
source-From SENT items and no other unmanaged items, drafts, Spam or Trash among
unmapped items. The inspector wrote neither Gmail nor business SQLite state.
A fresh-process offline production CLI status reopened schema v4 and reported
the same mapping/job counts, with degraded/stale status rather than false health.
Independent read-only, network-disabled acceptance recomputed all eight safety
checks against the journal/current SQLite and verified both backup artifacts.

## Remaining boundary

Continuous Compose service remains Created/stopped. This is bounded live
current-label/migration/continuation evidence, not complete Phase 1 acceptance,
an indefinite daemon, arbitrary historical expansion or unknown retry authority.
After v4 migration, do not select the old image against this DB or restore a
pre-insert snapshot after the twelve real writes. Safe fallback is stopped
maintenance retaining current durable state until a bounded repair is decided.
