# Continuous sync operations

Use the supplied non-root image on a local SQLite/WAL filesystem. After private
setup/OAuth and intentional scope selection, `docker compose up -d facet` runs
`facet run`: restart continues the saved scope, not a new historical expansion.
Use an immutable approved full-commit image/digest. Back up stopped, writer-locked
state/config/credentials before upgrades; do not restore a pre-insert DB against
a mailbox retaining later inserts. Keep deployments' proxies in private overrides.

The foreground owner waits at `--interval` after each cycle; when omitted it
uses `sync.poll_interval_seconds` (new configurations default to 60 seconds).
An explicit `--interval` overrides the configuration. This is **between cycles**,
not a total cycle duration/latency promise. One bounded `run --once`
may leave queued work; continuous run continues it. `sync --yes` intentionally
selects current rules and the fixed default six-month scope using the same guarded
granular operations. Do not use it merely to restart or silently expand scope.

Local stderr contains bounded JSON lifecycle/stage/count/elapsed events and
closed provider error code, reason, HTTP status, stage and retry delay when
available. Compose retains three 10 MB rotated files, restarts unless explicitly
stopped, and allows 90 seconds for graceful shutdown. A currently dispatched
request is not cancelled/replayed: it completes or its uncertainty is recovered
on restart. This grace is not a provider success guarantee. Logs may contain
necessary validated source EML hashes for unknown/fidelity diagnosis; do not
upload real logs to public tracking. No mail content/addresses/credentials or raw
exceptions are logged. Identical EML bytes have identical hashes; use private
attempt records for occurrence identity. Target raw hashes can differ legitimately.

The Dashboard reads only cached aggregate snapshots, refreshed by the owner
between pages/jobs and locally during the idle wait with throttling. Snapshot
freshness/heartbeat means the owner
published observations, not that Gmail or every job succeeded; in-progress
unverified cycles stay unknown rather than green. Counts are confirmed unique
mappings, not insert attempts or external agent outbound mail. `/healthz` means
HTTP alive; it is not proof that sync advanced. No hashes/IDs/mail details appear
in HTTP/DOM. Slow/unreachable provider calls can make snapshots stale honestly.

Before the first new project-job claim in a cycle, target inventory checks all
IDs including Spam/Trash/drafts. Proven mappings/known results precede outbound
classification. Unmanaged SENT/DRAFT requires a single normalized source From;
it is allowed but never adopted/counts as projection success. Other unmanaged
items or a failed/incomplete inventory stop new inserts with queued jobs intact;
source History ingestion/readback recovery are retained. Correct the external
condition and ordinary restart rechecks. Never delete/adopt implicitly. Missing
mapped mail is reported, not automatically inserted. Enumeration is not atomic
against external agents; no exactly-once or sole-mailbox-writer claim is made.

Domain discovery uses bounded Gmail From-domain candidate queries and strict
local dot-boundary/IDNA rule evaluation. Broad candidates are not admission;
no unfiltered source scan occurs. Concrete omitted eligible provider samples
require investigation; finite read-only probes do not prove exhaustive recall.
Live accounts/window/rules, deployment, new OAuth scopes/deletion and repair
retain their separate authorization boundaries. See current acceptance status,
not historical plan tables, before claiming Phase 1 or production dogfood passed.
