# Reconcile enqueue lineage correction

## Evidence and scope

After successful source reauthorization, the source-only run retained 100 seen
candidates, then failed with `persistence_failure` on its first matched unmapped
candidate. Database integrity is OK; mappings/insert attempts remain 4887/4889.
The real production-call regression first reproduces an AttributeError:
`_enqueue` reads message_id/thread_id, but DiscoveryCandidate exposes
source_message_id/source_thread_id. The CLI also creates the reconcile epoch
using `reconciler.run_id` but supplies the different request ID to `_enqueue`,
whose jobs reference the epoch by foreign key. The foreign-key mismatch is a
second static defect, not proven as the first cause of the live failure.

## Minimal implementation

- `src/facet/cli/reconcile.py`: pass the actual prepared reconcile run ID to
  `_enqueue` and use the real candidate source ID fields; preserve request-key
  idempotency and source-only transport.
- `tests/unit/test_reconcile_read_retry.py`: exercise production `_enqueue` with
  real SQLite foreign keys and a prepared epoch, including existing active thread
  and untracked admission if supported by the fixture. Check durable job lineage
  and duplicate enqueue behavior rather than mocking successful queue writes.
- Update current status with actual verification and remaining live gaps.

No schema, scope, retry policy, History cleanup or target operation changes.
Independent plan review precedes implementation; independent candidate review,
required full baseline and CI precede merge. Local candidate image verification
may precede PR under existing authority. Real follow-up remains source-only;
ordinary sync stays stopped while reconcile runs. Stop on unexplained storage,
binding, rule or generation failure; never reset DB or claim full coverage.

## Acceptance

Production enqueue succeeds against the epoch actually created by the CLI,
persists valid foreign-key lineage and does not duplicate a job on repeated
enqueue. Focused reconcile tests pass. Live run must classify every listed
candidate or explicitly retain incomplete coverage; mapping/insert counts must
remain unchanged during source-only maintenance. Original 217 History records
are outside this correction and remain untouched.

Independent plan review approved base `89cd15c` and the original plan digest
`82fb9708176aebfdf837933c0c75915e6d460199db39dfa0e5572f8eb0e90436`.
The regression will exercise the actual `run_reconcile` call site with real
StateOwner/SQLite and production scope, prepare, enqueue and epoch-close paths.
External source operations are synthetic; fixture config loading is stubbed,
not readiness for a claimed CLI subprocess gate. Cover tracked projection and
untracked expansion, epoch_jobs/FK lineage, durable classification, no Target
construction, unchanged mapping/attempt counts, and same-key terminal replay
without extra jobs/admissions. Retrying a failed live run uses a fresh key.
Existing interrupted running/draining same-key behavior is not validated by
this narrow correction; stop if that separate edge is encountered.

## Acceptance receipt

Independent implementation review approved code candidate `4f0ea6c`, ran 39
focused tests, and reproduced each old defect independently with in-memory
mutation checks. Root full baseline: 3004 passed in 876.62 seconds; required CI
passed. PR #122 merged at `ff6965991ea9d151bd02b0ce8f85d149cff72c7e`.
The corrected diagnostic image completed a real source-only run: 4769 listed and
read, 4761 mapped, 8 queued, zero 404/issues/seen. It recovered 2128 reads with
159.142 seconds cumulative waiting; durable elapsed was 2099.964693 seconds.
Maintenance mapping/attempt/legacy counts stayed 4887/4889/217, FK checks were
clean, and a locked backup was verified. Official image deployment succeeded;
ordinary sync remains blocked by target refresh `invalid_grant`. Target reauth
and completion of the queued projections are separate next steps, not claimed
by this source-only acceptance.
