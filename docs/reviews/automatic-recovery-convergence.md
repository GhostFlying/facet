# Automatic unknown checks and proven event convergence

2026-10-08. Root implementation; independent Sol xhigh review.

## Bound candidate and behavior

Approved plan SHA256
`3ede23881aa33bcab644380be5ffbbcd8854345497ad15790ca864961445fdee`;
independent acceptance binds source `6df5ca719dd5dd106bc66f072ed6e64f73bc9064`.
The source-404 diagnostic finding was fixed and affected-review passed. Earlier
unaffected review remains valid; no new ownership policy was introduced.

Normal `run --once` checks due pending unknown attempts before projection, stores
check count/deadline under the owned recovery claim, and never inserts or maps
an unproven result. Empty indexes are rechecked; unique content without ownership,
duplicates, fidelity mismatch and confirmed source loss retain precise attention.
Read-only `recovery check` shares the evidence reader and never mutates SQLite.
Known action-label removals are no-ops. Proven executed action aliases and exact
existing message effects close only their resolver bookkeeping, not business work.

Independent checks passed 149 focused cases, followed by 28 affected final-candidate
checks. A synthetic interrupted recovery check followed by a new owner safely
requeued and recorded one check, without mapping or resend. Root affected checks
passed, including actual external-only fake-provider CLI subprocess restart.
Final root offline checks passed **2884 tests in 720.00s**, locked dev dependencies,
Ruff lint/format, both CLI help/version smoke checks and repository safety.
No full-check rerun is required for receipt-only documentation.

## Local image and real-state copy

Exact non-root image `facet:6df5ca7` has revision label matching the source SHA and
image ID `sha256:f825bc92b344d80a3381b1f5ddc2db402ea7a0d790f1372246b278fb6cb54a52`.
Application source comes only from that image. Qualification uses a read-only
root filesystem, network disabled, private tmpfs, mounted synthetic tests and
test dependencies. All 76 production CLI/complete-sync/action-consumer cases
succeeded in the combined qualification invocation, including automatic unknown
checks, delayed indexing, fault retention, stopped generations and restart
without a second insert. That invocation as a whole was not green: its additional
unit fixtures assumed a writable working directory and a checkout source path.

The affected image unit subset passed 27 checks in 7.92s after correcting test
setup: a writable private working directory, explicit pytest root/conftest, and
the isolated reader's expected source path linked to **the image's own** `/app/src`.
The earlier harness errors were read-only working-directory/isolated-reader path
assumptions, not provider or production failures; those runs are not passing gates.
No host application source was overlaid and no tests/checks were removed. Thus
all 103 selected cases have passing evidence across the CLI/action and corrected
unit partitions; do not describe the initial combined invocation as a passed run.

A network-disabled diagnostic acquired the installed state's owner flock through
a read-only mount and used SQLite backup to make a private tmpfs copy including
WAL. Only the copy acquired a new application owner and ran the actual convergence
consumer. It completed 13 proven resolver events: attention 58 to 45; a second
pass completed zero. Mappings, attempts, rules, epochs, History checkpoint,
threads and action commands were unchanged. Original-volume writes and Gmail
operations were impossible in that diagnostic. This is not a live repair receipt.

## Remaining gates and limits

Required final PR CI is a merge gate; GitHub records its exact head/check/merge
state separately from this source acceptance. No live old-record repair,
new Gmail insert, deployment,
unknown resend, new backfill scope, long-running service or Release is authorized
or claimed here. The actual installed state remains at its earlier 4306 mappings,
58 attention and one protected unknown. The remaining 45 attention are not solved;
the old unknown's ownership/retry decision is still unresolved. A unique MIME match
or empty search is never treated as exactly-once proof.
