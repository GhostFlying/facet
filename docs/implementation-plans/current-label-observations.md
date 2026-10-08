# Current action-label observations

User decision: 2026-10-08. Base: `618887a070a19738618c3a7602df4d570b4a35be`.

## Delivery and simplification

Production History label notifications mark a source thread dirty. Read its
current non-draft message labels and act on the currently configured categories,
not on the old notification's label ID or add/remove direction. Missing/deleted
old IDs and currently absent tags are ordinary no-ops. Keep History ingestion
deduplication, but replace its business-command identity with a durable
per-thread/category observation. Persistent tags execute once; only observed
absence followed by presence creates another activation. Unobserved transient
tag changes are not reconstructed. Removal neither withdraws learned rules nor
reactivates stopped threads.

Reuse source metadata, exact label configuration, sender/domain normalization,
rule publication, admission/stop/job repositories, writer ownership and runtime.
Add three small fixed v4 tables: observations, current activation receipts and
initial-baseline page progress. Retain old action commands untouched as historical
evidence; do not reuse their History/label unique key for current activations.
New receipts have a local activation ID and per-observation sequence, reference
the actual triggering event for audit, and link the selected rule and resulting
thread admission/generation. Learned rules use normal enabled-rule admission;
receipts retain label provenance without fabricating legacy action-command IDs.
Effects, receipt, observation acknowledgement and label-notification completion
commit atomically. Provider snapshots are fetched outside that transaction.
Already tracked threads do not need another completed expansion job to learn a
rule. Stopped threads can learn rules but cannot be implicitly reactivated.
BlackList wins over simultaneous add tags for thread stopping.

Fresh initialization must persist initial H0 first, then baseline existing
action-tagged threads without executing them, holding operational consumption
until complete. This is a per-thread initial observation, not an instantaneous
mailbox snapshot. Upgrade must preserve proven executed legacy activations for
the matching current category/label, rather than suppress pending user actions
or a recreated/remapped label. Baseline queries are label-scoped, resumable and
zero-target-write. Provider failure is not absence. Construct the consumer even
with no currently available configured labels; observe absence before parsing
irrelevant sender headers. A single cycle reuses one snapshot per dirty thread.

## Files

- `db/migrations/v0004.py`, registry/schema/session/action-label version dispatch,
  and `runtime/state_owner.py`: backed-up v3-to-v4 upgrade (preserve v2-to-v3).
- `projection/current_actions.py` and a narrow repository: current observation,
  atomic normalized effects/acknowledgement and notification completion. No
  general capability framework or mail-content persistence.
- `gmail/source.py`, `runtime/foreground_runtime.py`, `sync.py`: snapshot reader,
  production dispatch and bounded recheck of historical label-only attention.
- Focused unit/integration and real CLI subprocess fake-transport tests; contract,
  spec, AGENTS decision override and concise current capability status.

## Acceptance and stop gates

Independent plan review before implementation; independent candidate review
afterward. Test old unknown label add/remove notifications with no current tags,
four message notifications producing one activation, restart/sticky tag/new
participant deduplication, observed absence/re-add, baseline, upgrade legacy
receipts, simultaneous categories, stopped generations, transient source errors,
transaction rollback and privacy. Exercise production CLI/runtime with fake
Gmail, not direct readiness/binding/rule/epoch injection. Run affected tests in
development, required full checks/CI at the final candidate and local image
validation before PR if wiring is uncertain. Preserve unknown insert recovery.

No live Gmail mutation, deployment, live DB migration, or cleanup is authorized
by this engineering change. Existing live attention counts remain unchanged until
separately scoped verification. A schema migration backs up SQLite via its backup
API plus private configuration/credentials before DDL; uncertain commits stop.
Do not broaden eligibility, infer old actions, reset mappings, replay inserts or
claim all Phase 1 gates. If baseline cannot be established safely, stop startup
with a concrete typed reason rather than silently executing legacy tags.
