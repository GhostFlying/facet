# History gap recovery through the production sync path

Date: 2026-10-07. Base: `b29543ae331619950eb3ce866dbc21b1735e8f69`.
Root owns implementation and current status; independent Sol xhigh reviews plan
and candidate. This implements existing M4-02 requirements, not a gate waiver.

User-approved simplification (2026-10-07): rule changes and message arrival do
not have a strict temporal ordering guarantee. Normal History processing and gap
admission use the effective rules selected at processing/scan time, not the rule
that would have applied at the message timestamp. Recovery may admit a message
earlier than rule creation inside the entire known downtime window. This is not
permission to scan arbitrary older history. Keep effective_at for audit/schema
compatibility; no historical ruleset reconstruction or schema migration.

## Observable delivery

After an expired History cursor, production `run --once` records H1 and preserves
the old checkpoint, durably scans active threads and the entire known downtime
admission window, consumes every History page from H1, then resumes ordinary
projection. A new process resumes partial work without duplicate inserts.
Granular init/auth/rules/preview/start/run remain the test entry; the separately
planned complete `sync` wrapper, daily reconcile, target audit, backup CLI and
broader Phase 1 gates are not claimed by this unit.

## Minimal implementation and reuse

- `projection/gap_recovery.py`: reuse existing typed gap/epoch/partition/job rows
  and repository guards. Select latest unresolved gap, prepare or resume one
  recovery epoch with its already persisted H1. Known window is reliable coverage
  minus existing five-minute safety margin through H1 observation, with no
  six-month/24-hour cap. Missing trustworthy coverage remains explicit attention;
  never substitute a guessed range or reset the cursor. Explicit unknown-range
  preview/approval commands remain a separate maintenance gate.
- Reuse the sealed current rules and existing query planner/local metadata
  admission for recovery discovery. Apply processing-time rule eligibility and
  current blacklist; stopped threads stay stopped. Gap queries use Google's
  documented Unix-second boundaries (rounded outward); metadata locally enforces
  exact window membership. Do not silently omit the final day or inherit PST
  interpretation from the existing date-only query. Only recovery enables the
  precise-window option; unchanged ordinary-backfill receipts stay valid.
  Preserve existing unsupported-domain-query refusal, not an unfiltered scan.
  Before each new gap admission, recheck the matched allow's current enabled
  revision in the publishing transaction. Rule removal/replacement during a
  paused/restarted recovery cannot keep authorizing new threads through the old
  snapshot; newly added allows do not widen this recovery's sealed query.
- `projection/backfill.py`: select the source-window partition explicitly when an
  epoch also has thread partitions. Recovery admissions use future-rule
  provenance, not historical-backfill authorization, and retain durable linking.
  Keep normal explicitly authorized historical admission unchanged.
- `projection/worker.py`: allow this coordinator to drain only its durable thread
  expansion jobs before H1 catchup. Existing full-thread metadata expansion
  creates/reuses project jobs, skips mappings and drafts and preserves unknown
  attempts. This phase cannot execute target insert or recovery jobs. Avoid a
  second message-copy engine or new general scheduler.
  Existing stable-key project jobs retain their original priority/state and
  attempt lineage when a recovery expansion links them; never recreate unknown
  work or fail solely because ordinary History originally used realtime priority.
- Active threads each receive a durable partition and generation-bound expansion
  job. Scan completion follows confirmed expansion; stopped selectors complete
  without work, source_missing is explainable, failed metadata does not silently
  become complete. Enumerate in bounded DB pages, refreshing the active set before
  sealing discovery. Partition/work and progress are committed together.
- `sync.py`: recover before ordinary discovery/poll/target worker when a gap
  exists; normal History 404 leaves a durable gap and returns controlled failure.
  On subsequent cycles, scan/expand first, then begin/resume a recovery-origin poll
  from H1. Only completed full pagination replaces the checkpoint and clears the
  polling gate via existing lineage checks. If H1 expires, the new durable gap
  supersedes recovery; preserve original reliable coverage and replay scans.
  Recovery epoch completion reflects pending/unknown/terminal issues, without
  keeping normal polling blocked after successful H1 catchup.
- `cli/bootstrap.py` / `cli/status.py`: ordinary service readiness is anchored to
  the authorized initial epoch, not a latest completed recovery epoch. Recovery
  progress and fixed expired-action warnings remain visible without reporting
  an unresolved gap as healthy; no extra public identifiers or content fields.
- `projection/admission.py` / `sync.py`: the existing prospective evaluation
  selects processing time for allow and blacklist eligibility. Use it for normal
  History and gap discovery; historical backfill keeps its authorized snapshot.
  Reuse the recovery-start current ruleset and stable query; no reconstruction
  of earlier rule versions or changing page queries after a rule addition.
  Public CLI/
  Dashboard warnings report unreconstructable expired label activations, never
  execute current labels or claim all lost actions were recovered.
- `gmail/source.py`: an explicit precise-window option renders Unix seconds;
  recovery uses history_candidate so original internalDate, rather than current
  discovery observation time, enforces only the bounded recovery window.
- Focused unit/CLI external-fake tests, one concise review receipt and current
  status. No schema migration, native/bootstrap defense, IPC or new framework.

## Acceptance and stop gates

Actual CLI subprocesses with production SDK/config/credentials/runtime and only
external Gmail/OAuth replaced: init/auth -> rule -> preview/start -> normal
mapping -> History 404 -> durable H1/gap with unchanged cursor and zero insert ->
next process recovery scan -> H1 pagination -> missing messages/new eligible
thread insert/readback/map -> restart no duplicate. No DB seeds of binding,
rules, readiness, epoch or gap. Fault source scan/page/catchup, restart each phase,
expire H1 again; unknown insert stays pending with no resend. Cover admission of
pre-rule messages inside the known gap but not outside it, processing-time rules,
stopped generations, all active threads, downtime longer than
six months, exact same-day boundaries, empty rules, unknown coverage refusal and
current labels never replacing expired events. The existing rules-remove CLI is
not implemented; do not add a separate maintenance/journal implementation to this
unit. Test allow removal between failed gap pages through the typed policy
repository in a focused unit test: remaining untracked threads are not admitted.
The complete CLI E2E does not seed rule/binding/epoch/gap rows; missing rules-remove
command remains a distinct final maintenance gate.
Privacy sentinels check DB/journal/
files/logs/CLI/HTTP; public output uses only existing allowlisted aggregate fields
and fixed warnings. No network waits inside SQLite transactions.

Iterate affected tests; exact final candidate receives prescribed full offline
checks, independent implementation acceptance and pinned non-root local image
E2E before PR/required CI. No real-state run/start/insert, source mutation, cleanup,
unknown retry, scopes, daemon resume, deployment or Release in this engineering
unit. After offline/container acceptance, resume separately authorized live tests
only within their concrete account/rule/window scope and current target checks.
Stop for a real contract conflict, absent coverage/range authorization, privacy
failure or a proposed state reset/retry; do not expand hardening or waive gates.

## CI execution budget and ordered integration (2026-10-08)

The reviewed runtime remains unchanged. PR #96's Python 3.13 full checks passed;
Python 3.12 was cancelled by the configured ten-minute job limit, with GitHub's
explicit maximum-execution-time annotation, not an assertion failure. Increase
only `.github/workflows/ci.yml`'s checks job budget to twenty minutes. Keep both
Python versions and every safety, locked dependency, lint, formatting, full-test
and CLI smoke step. Verify the workflow-only diff, repository safety and a
focused independent review; final candidate CI must complete before merge.
Existing runtime/image reviews remain valid for unchanged inputs.

Then integrate the reviewed parent dependencies and PRs #93–#96 into main in
dependency order, checking actual base ancestry and CI rather than merging into
an unpublished temporary branch. Use the final main-SHA image for the user's
approved current-host granular historical test after preserving private state
and checking the existing accounts, scopes, target and original window. No new
rule/window scope, old unknown retry, cleanup, source mutation, continuous daemon
resume or Release is authorized by this budget correction or integration.
