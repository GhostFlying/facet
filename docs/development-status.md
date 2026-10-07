# Facet development status

Updated: 2026-10-07 (PRC; historical UTC receipts retain their original dates)

This is the durable handoff for autonomous development. Update it with evidence
at the end of each coherent implementation unit. Do not store account addresses,
mail identifiers, private fixtures, tokens, or raw diagnostics here.

## Current state

### Current live gate and insert adapter correction

The recent local build/Compose acceptance is not yet a working live projection.
The real state was backed up with SQLite's backup API plus private config and
credentials while the service was stopped. Existing action-label configuration
was preserved. A bounded production `run --once` refreshed credentials and
consumed History but confirmed zero mappings; one existing unknown insert
remains in recovery and was not retried. Read-only recovery search found no
candidate, which is not proof authorizing another insert.

Read-only target inspection found unexpected/unmanaged content, including a
draft, while the DB had no mappings. No further target writes or long-running
service startup are permitted until the operator resolves that target
prerequisite. No mailbox cleanup, claiming, scope expansion or DB reset occurred.
New message events on untracked threads also remain attention: incremental
admission needs a further product-path correction, not an all-success claim.

The concrete insert blocker was reproduced offline with the locked real Google
client: `neverMarkSpam` is not supported by `messages.insert`, so request
construction raises before HTTP. The bounded fix removes that keyword and adds
real-discovery tests with only HTTP substituted, including Date policy, thread
anchor, exact raw bytes and single-attempt provider failures. Four new cases
failed on the old adapter; 90 focused adapter/worker/CLI cases pass after the
fix. Independent implementation review approved exact candidate
`1b09b8f629d00e7ba7573e311ff6c764664d76fe`; see the
[bounded review record](reviews/gmail-insert-discovery-compatibility.md).
The unchanged Dockerfile built on sgbox and the resulting non-root local image
passed actual-client request construction with networking disabled. On an
isolated synthetic Compose volume, production CLI subprocesses completed init,
fake authorization/binding, sender rule, preview, explicit start, insert/readback
and durable mapping; a second process confirmed the mapping without another
insert. No readiness, rule, binding or epoch was seeded directly into the DB.
The shared-fake alignment follow-up at
`9d2d6ef1b799c10c864eab461cb27957538255e0` was independently approved and
passed the complete offline suite: 2653 tests. Repository Ruff/format, locked
environment sync, CLI help and safety checks passed. Production source and
image build inputs did not change in that follow-up, so the prior local image
evidence remains valid. No CI/merge/publication, real-service upgrade or
successful live projection is claimed.
Container Google connectivity also needs an environment-specific solution;
temporary host-network/IPv6 resolution overrides proved the bounded live CLI
path, not a generally usable Compose network or public Dashboard deployment.

Next live gate: the operator resolves the dedicated-target prerequisite; the
existing unknown attempt stays in recovery until an authorized, evidence-based
recovery action is available. Next engineering gaps are incremental admission
for new untracked message events and a usable container Google network path.

The package ledger below retains historical package evidence; it is not the
current executable-command checklist. The current live result and next gaps
are stated above.

| Unit | Status | Evidence / remaining gate |
| --- | --- | --- |
| Phase 0 Gmail spike | Complete within its scope | See [redacted results](phase-0-gmail-spike-results.md); production behavior not implied |
| Repository bootstrap | Complete | Public `main` published with account noreply identity; Python 3.11/3.12 offline CI passed |
| Phase 1 execution planning | User G0 approved; plan integrated | Exact approved/merged `caba7c7`; independent review/QA and candidate/main CI passed; not milestone completion |
| P1-00 execution baseline | Integrated | PR #6 exact `2618eaf`; independent plan/implementation review, candidate/main CI passed |
| P1-01 core/writer ADRs | Reviewed and integrated design freeze | PR #8 exact `09031e7`; core-v1/writer-v1, independent review and candidate/main CI passed; no runtime/G1 claim |
| P1-02 test foundations | Reviewed and integrated, including mandatory CT | PR #12 exact `1b7cd58`; independent review, candidate/main CI and 92 core-compatibility cases passed; Issue #5 closed, later feature-consumer tests remain |
| M1-01 package/config/CLI foundation | Reviewed and integrated | PR #11 exact `b1e4ae0`; 287 offline tests, independent whole/closure reviews, 3.12/3.13 candidate/main CI and installed-wheel checks passed; not complete init/CLI/G1 |
| M1-02 persistence | Finite SQL/DB21/action library and combined input accepted, unmerged; whole gate open | Corrected `c0bb4b0` and normal carry `a9c4e36` independently accepted with fresh exact CI; combined 1625 full tests and wheel passed; PR #15 remains Draft/open/unmerged, historical `62d75c0`/`2466834` HOLDs retained; actual provider/RV11, released migration source, restore and whole DB-01..28 remain |
| M1-03 writer/runtime/CLI | Bounded writer foundation and corrected Thread harness integrated; production sync owner open | PR #20 exact `ea80db2` and PR #22 exact `befe278` actually merged after nonauthor review and candidate/main dual-Python CI; corrected harness retains production OS bytes, 150 focused/758 full tests; no-state bootstrap source separately released, not accepted provider/actor/credential integration |
| M1-04 OAuth/binding | Early pure values/codec/client parser integrated; full package open | PR #18 actually merged exact `ff77e63`; 120 OP/608 full tests, independent source/head review, wheel and candidate/main 3.12/3.13 CI passed; actual OAuth/profile/files/publication remain |
| M1-05 public status/privacy | Early pure/logging library integrated; full consumer gate open | PR #16 actually merged exact `f209fbe`, independent review and candidate/main CI passed with 488 offline tests; actual DB/auth/runtime/HTTP/DOM/Compose consumers still pending |
| M1-06 authentication/initialization | Metadata/rule admission implemented; live Gmail gate open | User decision on 2026-10-05 formally removed source-path attestation and Facet-side sender-authentication from automatic admission. DKIM/DNS provider and evidence seam were deleted; source candidates now use Gmail metadata, account binding, visibility/draft checks and exact rules. Legacy `rules.authenticity: require_trusted_auth` is read-only compatibility and omitted on write; persisted `auth-v1` remains a stable rule token. Focused and full offline tests are the current evidence; no live Gmail operation has been performed. |
| M1 foundation as a whole | Incomplete | `facet init`, production OAuth/profile ownership, and the non-fake `run --once`/`backfill start` dispatch seams remain. Source-path attestation is no longer a product gate; full maintenance CLI, controlled live Gmail verification and G1 remain open |
| M2 automated projection core | Foreground synthetic vertical integrated | PR #45 merged at `0a928369c8a1ee4f0684f7e4605899fec42af021`; fixed-window discovery, H0→History pagination, typed candidate/admission bridge, action-label effects, serial projection/readback, pre-dispatch recovery, and durable attention/retry convergence are offline-tested. This does not claim CLI/OAuth, live Gmail, Dashboard, Compose, Actions or Phase 1 completion |
| M3 continuous recovery and Dashboard alpha | Foreground aggregate and action-label consumers integrated; recovery remains open | PR #55 and PR #57 merged at main `5b6097f`; one-process `facet run` publishes aggregate snapshots, gates Gmail on verified bindings plus explicit backfill start, and composes readonly action-label effects; no live-account claim |
| M4 complete maintenance CLI and advanced rule maintenance | Recovery inspection candidate reviewed; CI pending | `facet recovery list/show/check` now inspect aggregate or private unknown-insert evidence without insert/retry/SQLite mutation; queue/review mutation, recovery preview/retry/repair, BlackList competition, offline backup/restore and optional label cleanup remain open |
| M5 self-hosted delivery | Immutable image workflow integrated and first image published | Main `1a42938`; PR multi-arch no-publish build and main publish passed; public GHCR SHA tag, digest, anonymous pull, amd64/arm64 manifest and UID 10001 smoke verified; host deployment/Nginx remain open |
| M6 real deployment and v0.1 | Not implemented | Backup/restore, live Gmail, selected host and 72-hour evidence |

Both `facet` and the isolated `facet_spike` are now packaged for Python 3.12+.
Production imports/CLI never adopt spike cursors/tokens. The foundation tests cover
closed types, strict YAML, no-follow private reads and real CLI subprocess
JSON/exit/privacy/zero-effect behavior, alongside all existing spike tests. They
do not verify a production sync process, trusted admission, backfill, History ingestion or rendered Dashboard.

The integrated M1-05 early library adds independent allowlisted public models, a closed
error catalogue/serializer and fail-closed structured logging. It does not expose
HTTP or read actual DB/auth/runtime state. Real snapshots and raw third-party
OAuth/provider logger consumers, browser/DOM and Compose remain later gates;
Issue #14 stays open. M1-04's current pure slice contains closed credential value
models, an in-memory byte envelope codec and a strict Desktop-client parser. It
does not open private files, create capabilities, invoke OAuth/Gmail, fetch profiles,
refresh or publish credentials, or make a production binding ready. Issue #17 stays
open. PR #18's actual integration and successful main CI are recorded below.

The user's latest model policy on 2026-10-02 permits only Sol high/xhigh or Luna
for prospective tasks. Complex design and high-risk independent review use Sol
xhigh; Astra receives no new work or reactivation. Earlier authorized reviews
retain their actual model/reviewer/SHA attribution. G1-G6 remain incomplete.

本次交付顺序已按用户 2026-10-03 的纠偏决定更新：第一条产品能力是自动
discovery、固定六个月 backfill、History 全分页/cursor/事件去重、readonly action-label
规则更新和可恢复投影；不以手动选择 thread 或 one-shot 复制为入口。产品没有同步延迟
承诺。支持运行模型是官方 Docker image 内一个前台 sync/writer 进程；runtime/native/
read-bootstrap 证明、独立 daemon/IPC/request receipt、跨 thread 并发四路、实时优先、
公平调度和复杂 raw budget 不再是第一交付或 milestone gate。它们不代表已删除的代码，
而是从当前关键路径移除的工程方案。

## Latest product-first handoff (2026-10-05)

The user formally deleted source-path attestation and sender-authentication as a
Facet automatic-admission requirement. Gmail remains responsible for SMTP
authentication and mailbox classification; Facet does not claim sender or
content safety. The current candidate uses metadata/rule admission, keeps raw
mail only for target projection, and retains all account, scope, privacy,
single-writer, durable-ordering and unknown-insert recovery defenses. Historical
DKIM/attestation notes below are retained as evidence of prior candidates, not
as active gates.

- The former PR #71 DKIM/source-attestation implementation is superseded and
  removed. Its historical evidence is not a current product gate. The active
  candidate's next product-bearing delivery is the complete CLI vertical path
  with fake Gmail/OAuth transport, followed by a separately authorized
  controlled Gmail run.

- Historical PR #73 (`8c241c8d62c92426815664a9957cdfadbd2bec36`) proved the
  earlier signed-fake CLI path. Its DKIM/provider-specific admission behavior
  is superseded by the 2026-10-05 decision and is not a current gate. The
  durable CLI evidence (init, role authorization, sender rule, write-free
  preview, explicit start, discovery, insert/readback, mapping and restart
  continuation) remains valid and is re-tested by the metadata-only candidate.

- Candidate `aa646bb` adds `facet recovery list/show/check`.
  It creates an unknown insert only through the production insert-intent path in
  the synthetic command test, then searches and reads back target evidence
  without a second insert or SQLite mutation. Duplicate, missing and changed
  evidence stay attention. Independent implementation review is approved; the
  focused 61-test set and all 2546 non-flaky tests pass, while one existing
  full-process FD-snapshot test remains environment-flaky (isolated rerun and
  its file pass). Full candidate CI, recovery retry/repair and live Gmail are
  not claimed.

- The next product-shaped candidate composes the existing foreground sync owner
  and aggregate Dashboard in one supported process. `facet run` without
  `--once` validates managed configuration, retains one SQLite writer owner,
  runs the existing foreground cycle, and publishes only allowlisted in-memory
  snapshots to the fixed read-only HTTP routes. `Dockerfile` and Compose now
  use this foreground entrypoint with the persistent `/var/lib/facet` state
  volume; `facet run --once` and `facet web` remain separate commands.
- The candidate handles listener startup failure and SIGINT/SIGTERM with owner
  cleanup. Snapshot freshness uses a monotonic clock; failed collection
  invalidates readiness, and unknown discovery totals/rates remain null. The
  Dashboard reports lifetime confirmed mappings separately from current-epoch
  discovery and surfaces durable discovered/completed thread-job counts and
  partition-level attention without exposing message details, rules, addresses,
  IDs, or provider payloads. Scanned-thread count remains explicitly unknown
  when the DB has no safe aggregate for rejected candidates.
- The candidate now gates every provider cycle on DB-only verified bindings and
  an active, explicitly-started epoch. Before that gate passes, it publishes a
  blocked/unknown aggregate snapshot and does not construct or call Gmail.
- PR #55 is integrated at main `e2b9b1727cbbe2743d1b887e9ec3d2250bc61431`.
  Independent implementation review approved the corrected exact candidate
  `bbddd4c`; the final offline suite passed 2516 tests, focused evidence passed
  52 tests, and candidate Python 3.12/3.13 plus no-publish image CI passed.
  This proves the supported one-process composition and aggregate Dashboard,
  not live Gmail projection, action-label
  production wiring, or Phase 1 completion.
- The next product-critical delivery is production action-label consumer wiring
  plus the remaining recovery boundaries. A real
  Gmail run still requires explicit live-account/test-scope authorization; no
  such operation was performed by PR #55.
- PR #57 is integrated at main `5b6097f3f0a6e0ab2a0bf55157a9e9f7518bf5a8`.
  The historical all-three-label precondition is superseded by the approved
  partial-map correction now under local validation: any nonempty configured
  subset composes the existing durable `ActionEffectConsumer`, while missing
  categories remain unmapped and their events stay explicit attention. All
  labels absent still leaves ordinary sync running without an action consumer;
  duplicate labels and malformed/provider failures remain typed failures. This
  correction has not yet been merged or live-verified, so the prior candidate
  evidence remains historical and does not prove a Gmail action event.

- The offline maintenance CLI unit is integrated in PR #59 at main merge
  `2033be505e36217da7dbaf2b547caeef5819260b` (implementation candidate
  `c4779ac39d6e56bc5214abd3c8aba33bb077847`; plan:
  `implementation-plans/m1-status-doctor-cli.md`). `facet status --json` and
  `facet doctor --json` read the managed SQLite WAL through one deferred,
  read-only transaction without taking the writer lease or constructing
  Gmail/OAuth clients. They reuse the four aggregate Dashboard DTOs, report
  offline snapshots as stale/unknown rather than fabricating live health,
  retain typed doctor findings with catalogue exit codes, and privately check
  both declared/verified role addresses plus projection binding consistency.
  Nine focused subprocess tests pass; the complete local offline suite passes
  2528 tests, with Ruff, format, safety, wheel smoke, and candidate/main CI
  passed. SQLite's normal `-wal`/`-shm` coordination sidecars may appear on a
  read snapshot; no business rows, config, credentials or mail content are
  written. This closes only the offline status/doctor unit, not the complete
  CLI, live Gmail, recovery, deployment or Phase 1
  gates.

- The exact domain-rule mutation is integrated in PR #61 at main merge
  `6a2a5d7` (implementation candidate `7c7ae20`; plan:
  `implementation-plans/m1-cli-domain-rule.md`). `facet rules add-domain`
  reuses the existing single-writer ruleset publication and request replay
  path, applies the existing PSL/IDNA/public-suffix policy, and refuses new
  mutations while bindings are pending. The candidate passed 43 CLI bootstrap
  tests, 105 related rule/admission/action tests, 2530 full offline tests,
  Ruff/format/safety, wheel import/help smoke, independent implementation
  review, and Python 3.12/3.13 plus no-publish image CI. This adds maintenance
  rule control only; it does not resolve live Gmail, recovery, or final Phase 1
  gates.

- The explainable backfill-preview unit is integrated in PR #63 at main merge
  `440b0de` (implementation candidate `3d62c21`; plan:
  `implementation-plans/m2-cli-preview-explainability.md`). Preview JSON now
  reconstructs its persisted fixed window, discovery cutoff, ruleset revision,
  explicit-start requirement, thread-wide disclosure semantics, and
  `target_writes: 0`; replay returns the same scope. The candidate passed 52
  CLI/status tests, 46 backfill/epoch/sync tests, 2530 full offline tests,
  Ruff/format/safety, wheel help smoke, independent review, and Python
  3.12/3.13 plus no-publish image CI. This closes preview explainability only;
  it does not resolve live Gmail, recovery, deployment, or final Phase 1 gates.

- The aggregate maintenance-view unit is integrated in PR #65 at main merge
  `535e096` (implementation candidate `4835a42`; plan:
  `implementation-plans/m4-cli-aggregate-views.md`). `facet backfill status
  --json`, `facet queue list --json`, and `facet review list --json` reuse the
  existing offline, read-only status snapshot and expose only progress, queue
  counts/oldest runnable age, or categorized issue groups. Guarded subprocess
  tests confirm no Gmail/OAuth import or network access, no writer lease or
  mutation, and no account/path/message details in output. The candidate passed
  61 CLI tests, 2531 full offline tests, Ruff/format/safety, independent
  implementation review, and Python 3.12/3.13 plus no-publish image CI. Item
  inspection, retry/approval, recovery, and repair commands remain open; this
  is not complete maintenance CLI or a Phase 1 gate.

- The persisted-rule inspection unit is integrated in PR #67 at main merge
  `21c17d7` (implementation candidate `5613113`; plan:
  `implementation-plans/m1-cli-rule-views.md`). `facet rules list --json`
  reports only the sealed current ruleset revision and rule count. `facet rules
  show --rule-id <id> --private-metadata --json` reads one current rule's
  private value, revision, effective time, origin, and policy metadata; public
  show is rejected and missing/foreign selectors do not disclose existence.
  The read path is offline and SQLite read-only, with no Gmail/OAuth import or
  writer lease. The candidate passed 62 CLI tests, independent implementation
  review, Python 3.12/3.13 CI, and no-publish image build. Rule deletion,
  blacklist mutation, and item-level review/recovery operations remain open.

- The read-only queue-item inspection unit is integrated in PR #69 at main
  merge `4a23c06` (final implementation candidate `4b5adaa`; plan:
  `implementation-plans/m4-cli-queue-show.md`). `facet queue show --job-id
  <id> --private-metadata --json` returns only typed job/source-thread IDs,
  kind/state/priority, attempts, error code, and timestamps from the configured
  projection's SQLite snapshot. Malformed selectors return `invalid_input`,
  well-formed public selectors return `scope_required`, and absent/foreign
  selectors return `owner_unavailable` without existence disclosure. The
  candidate passed 63 CLI tests, a focused precedence fix review, Python
  3.12/3.13 CI, and no-publish image build. Queue retry/claim/cancel/recovery
  remains unimplemented; this is not complete maintenance CLI or a Phase 1
  gate.

- The bounded Dashboard/Compose HTTP unit is integrated on main `e2b9b17`
  after independent plan approval. `facet web` serves only the
  allowlisted aggregate routes (`/api/v1/status`, `/api/v1/progress`,
  `/api/v1/issues`, `/api/v1/diagnostics`, `/healthz`, `/readyz`) through a
  silent fixed-output HTTP handler. Until a runtime collector publishes a
  snapshot, every aggregate response is explicitly `unavailable`/`unknown`;
  GET does not call Gmail, DB, or provider I/O. The bundled page contains only
  aggregate fields. Compose runs one non-root UID 10001 web process on
  container `0.0.0.0:8080`, published only to host loopback, with a persistent
  `/var/lib/facet` volume and read-only root filesystem. Seven focused web/
  subprocess tests pass; full offline suite is 2508 passed. Docker Compose
  config parses. The bundled image and actual non-root container smoke are
  recorded in the image handoff below. This is an HTTP/container boundary
  fixture, not a usable live Gmail deployment or Phase 1 completion. Plan:
  `implementation-plans/dashboard-compose-alpha.md`.

- The immutable image delivery unit is integrated on main `1a429386f7670ae11f211e21105b19a6587f59f7`.
  Dockerfile uses the frozen Python manifest and `uv sync --locked --no-dev`.
  PR #51's Python 3.12/3.13 checks and multi-architecture no-publish Buildx
  job passed. The main publish job passed at run `37200289682`, publishing only
  `ghcr.io/ghostflying/facet:1a429386f7670ae11f211e21105b19a6587f59f7` with
  manifest digest `sha256:9fcbb5b46fcbffd2df79072613be6eb8fd68f94349ccb76ead08c322f2ea6e41`.
  Anonymous `skopeo` inspection and pull verified the public manifest contains
  linux/amd64 and linux/arm64; a temporary container ran as UID 10001,
  returned `{"status":"ok"}` from `/healthz`, and correctly reported
  `{"status":"unavailable"}` from `/readyz`. This proves artifact delivery,
  not live Gmail sync, host deployment, Nginx, or release completion. Plan:
  `implementation-plans/image-delivery.md`.

- The next bounded CLI slice is implemented locally on top of main: plan
  `docs/implementation-plans/m1-cli-bootstrap.md` was independently approved.
  `facet init` now serializes the closed config schema, creates private SQLite
  state with the caller's exact request namespace/nonce, atomically publishes
  `config.yaml`, and can replay a completed or incomplete bootstrap without a
  second database. `facet run --once` opens managed state and stops at
  `binding_pending` before any Gmail/provider construction. Focused subprocess
  evidence is `tests/cli/test_init.py` (8) plus the retained CLI suite (40);
  exact candidate review and Python 3.12/3.13 CI passed on `37dd244`; the
  bootstrap slice uses
  explicit request IDs only; the complete G1 TTY journal/generation protocol,
  OAuth/profile verification and a real Gmail service factory remain open.

- PR #45's first candidate was held by implementation review for three concrete
  gaps: readiness was checked too late, the production candidate/admission seam
  was not connected, and unsupported History jobs stayed queued. Revision 1 of
  `m2-foreground-sync-cli.md` narrows the repair to those gaps. The current
  unmerged candidate adds a preflight before any provider call, a
  `SourceCandidateAdmission` adapter over `SourceAdapter.candidate`, and
  durable `needs_attention` versus due-only `retry_wait` handling. The prior
  exact candidate had 39 focused and 2473 full offline tests; this follow-up
  adds a runner-level due-retry test. It remains synthetic/offline evidence
  only until the new exact review, full CI and merge.

- The first product-shaped foreground composition is now implemented locally
  (candidate not yet merged): `ForegroundSync.run_once` reopens an initialized
  owner, resumes pre-dispatch claims safely, completes fixed-window discovery,
  creates/resumes the initial H0 History poll, persists typed events before the
  cursor, resolves tracked `messagesAdded` events, consumes readonly action
  labels through the typed source bridge, and drains the serial projection
  worker to target readback and mapping. The initial epoch remains `DRAINING`
  as the explicit live authorization epoch for subsequent checkpoint action
  effects. No daemon/IPC/runtime-bootstrap layer or disk raw spool was added.
- Plan `docs/implementation-plans/m2-foreground-sync-cli.md` was independently
  approved after revisions covering outside-transaction candidate/auth facts,
  aggregate `epoch_partitions.state=needs_attention` for unknown admission,
  H0 poll creation, message-added resolution, restart claim boundaries, and
  the retained live authorization epoch. Synthetic vertical evidence is
  `tests/unit/test_sync.py`; the focused set passed 38 tests and the exact
  offline suite passed 2469 tests. This is implemented/offline-tested only;
  it is not live Gmail, CLI-complete, deployment, or Phase 1 acceptance.

- The next bounded runtime-wiring plan
  `docs/implementation-plans/m2-cli-runtime-wiring.md` was independently
  approved and is implemented locally on the merged main base. The new
  composition performs profile probe, expiry/account/scope verification,
  pending-binding publication, access-only service construction, and then
  invokes the existing `ForegroundSync` through one injectable factory seam.
  Synthetic evidence is `tests/integration/test_foreground_runtime.py` plus
  the credential consumer/manager suites (36 focused tests); the Google
  factory never receives refresh tokens and no provider payload is persisted.
  This is offline-tested only. The CLI still stops at its preflight until the
  production OAuth command and persisted-rule admission loader are delivered;
  no live Gmail operation has occurred.

- M1-04 credential binding is integrated through PR #35 recovery head and the
  separately reviewed explicit-scope follow-up PR #37. Main contains
  `4c07766` and `a61c474`; both Python lanes passed for the follow-up. The
  remaining non-gate hardening note is cleanup of a manager-owned `.pending`
  temp file after a pre-replace write/fsync failure.
- Historical M2 PR #36 is integrated at main `28077e4`. It delivered only the fixed,
  offline policy/rules and typed attention-first admission seam: exact sender/
  domain matching, bundled PSL/IDNA, blacklist/effective-at boundaries, and
  lineage-bound `auth-v1` rule-token checks. Its final implementation review
  approved exact `6b13ca7` as bounded pure preparation only; focused 39 tests
  passed and candidate Python 3.12/3.13 CI passed.
- This historical preparation was not automatic admission, G2, or the first
  runnable production sync. The current action-label consumer and production
  History/Backfill wiring are tracked separately. No Gmail, target write, DB
  mapping, or live-account operation was performed by that unit.
- PR #41 is the first integrated durable action-label consumer on main at
  `fbb9fc8048239ae10a7620ddf7e179fa09172eb8`. Synthetic SQLite/WAL tests cover
  AddSender, AddDomain, BlackList, draft-only attention, retryable source
  failures, and file-backed restart replay without a second source read. The
  final candidate `cd50e2f93d7258868a7bb61d0af242aee9ec59c8` received an
  independent implementation review with no P0/P1 findings; 361 focused
  consumer/integration tests and the full 2450-test offline suite passed,
  together with Ruff, wheel import smoke, Python `-S` import, safety, and
  candidate Python 3.12/3.13 CI. It does not call Gmail or target APIs. The
  next production-critical seam is real source History/Backfill discovery and
  worker wiring; M2 and the first runnable production sync remain open.
- The bounded serial projection worker implementation is prepared in candidate
  commit `39215847c3165174dc5c8f1165d5fcb5ebe62398` on reviewed main base
  `5dd9b06fe0828fb4052efda22b721f170a1a82a8`. It expands admitted threads from
  typed metadata, excludes drafts, inserts one in-memory raw message at a time,
  verifies target MIME semantics/thread facts, persists mappings, and leaves
  uncertain insert outcomes in recovery without a blind retry. Synthetic
  temporary-owner tests cover two-message ordering/anchor reuse, target
  readback, replay-safe no-op reruns, raw/privacy sentinels, and response loss.
  Twenty-eight focused worker/adapter tests plus expansion/result tests passed;
  complete offline regression and independent implementation review are still required. CLI
  execution, History scheduling, recovery attribution, stale-claim takeover,
  Dashboard, Compose, Actions and live Gmail remain open.

## Active implementation record

- On 2026-10-02 the user explicitly approved G0 at
  `caba7c73895a303d329cf3eba1c89557530c38c5` and requested multi-agent execution.
  [PR #2](https://github.com/GhostFlying/facet/pull/2) is actually MERGED at that
  SHA via normal fast-forward. Independent technical review/QA and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36968387054)
  passed; [main push CI](https://github.com/GhostFlying/facet/actions/runs/36969107636)
  also passed Python 3.11/3.12. No force, platform merge commit or rule change.
- [P1-00 plan](implementation-plans/p1-00-execution-baseline.md) r2 received
  independent approval at SHA-256
  `b77d4f90d44ea61aad286851454e9db7d98cef0e1c703ad5968470e4d7242bae` before
  implementation. [PR #6](https://github.com/GhostFlying/facet/pull/6) actually merged
  at `2618eafad817aee4e491aa87ebede0f44f27a20b` after independent implementation/
  acceptance approval and [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36970748778);
  [main CI](https://github.com/GhostFlying/facet/actions/runs/36971068807) succeeded.
  The shared current-state
  docs owner and 36 actual package states are in [the ledger](phase-1-progress.md).
  Initial Issues: [P1-00 #3](https://github.com/GhostFlying/facet/issues/3),
  [P1-01 #4](https://github.com/GhostFlying/facet/issues/4),
  [P1-02 #5](https://github.com/GhostFlying/facet/issues/5).
- Independent startup baseline QA on main `caba7c7` passed Python 3.11.2,
  24 offline tests, Ruff lint/format (33 files), spike CLI help and safety.
  This preserves the spike baseline; it is not production Python 3.12/runtime,
  Gmail, Compose or maintenance verification.
- P1-01 [PR #8](https://github.com/GhostFlying/facet/pull/8) actually merged exact
  `09031e723af1ef6590dc6746744ee52894501e38`, after independent reviewer
  `phase1_plan_review` approved the corrected candidate and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36974129495) passed.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36974823051) passed
  Python 3.11/3.12. Frozen core `p1-core-v1` and writer `p1-writer-v1` are engineering
  inputs, not evidence that storage/writer/recovery runtime exists or G1 is closed.
- M1-01 [plan](implementation-plans/m1-01-package-config.md) r3 received independent
  approval at SHA-256 `feeabe53d454c931da343964aa7d0a923508d86d3710a03e7c69dc413d534101`
  before coordinator dispatch. The integrated foundation implements 47 canonical core
  exports, strict bounded YAML/config defaults, safe standalone config reads and
  actual `facet config validate/show`, with empty mutable-field registry. Init/apply
  and managed reads are controlled unavailable; no temporary writer/view protocol.
  Local locked checks passed CPython 3.12.13 with SQLite 3.53.1: 149 foundation-snapshot
  tests (24 retained spike plus 125 new), then 287 full tests after the normal merge
  of reviewed P1-02 partial inputs, Ruff lint/format (69 files), both entrypoint help and wheel
  build/non-editable install smoke. Dependency bootstrap used authorized network;
  production tests made no Gmail calls and subprocess guards forbid network/spike/DB
  imports. The preexisting local 3.13.5 lacks `_sqlite3`; it is not a full-runtime
  verification substitute. [PR #11](https://github.com/GhostFlying/facet/pull/11)
  actually merged exact `b1e4ae08f7e361518eaa4f7fb1ae9f7f0b278f28` after independent
  whole/affected-boundary approval and [revised candidate CI](https://github.com/GhostFlying/facet/actions/runs/36980149544).
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36980646059) passed
  Python 3.12/3.13 at the same SHA. [Issue #7](https://github.com/GhostFlying/facet/issues/7)
  is closed only for this foundation, not Gmail/deployment/G1 or the full CLI.
  The earlier combined candidate `f00cf27` independently passed whole review and
  3.12/3.13 CI, but the coordinator held merge for two parser/help corrections.
  Current revised candidate adds specific child text/JSON help and canonical
  `config apply --file` parsing; apply still reads/writes nothing and returns
  unavailable. Twelve additional subprocess regressions and the required revised
  exact-SHA review/CI passed before integration; the earlier hold is historical.
- P1-02 provider/helper partial [PR #10](https://github.com/GhostFlying/facet/pull/10)
  actually merged exact `c18bfbee09b985ee7b9bb5c230ee2a70427c7edc` after independent
  reviewer `phase1_plan_review` approved the metadata-format correction and
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36978399171) passed.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/36978909460) passed
  at the same SHA. This partial slice supplies synthetic API/fault/privacy helpers,
  not, by itself, a completed P1-02 compatibility gate. M1-01 preserves its atomic core/config
  commits and normally merges that reviewed input without history rewriting;
  the combined tree requires a new whole-candidate review and 3.12/3.13 CI.
- P1-02 mandatory compatibility [PR #12](https://github.com/GhostFlying/facet/pull/12)
  actually merged exact `1b7cd58b4846aab86edcbb781a999abb968d047c`, consuming reviewed
  merged M1-01 types. Independent review, 92 CT cases/379 full offline tests,
  [candidate CI](https://github.com/GhostFlying/facet/actions/runs/36981977390) and
  [main CI](https://github.com/GhostFlying/facet/actions/runs/36982879970) passed.
  Issue #5 closed and the engineering dependency for M1-02 released; this does
  not validate future Gmail/repository/runtime feature consumers.
- M1-02 [Issue #9](https://github.com/GhostFlying/facet/issues/9) / [Draft PR #15](https://github.com/GhostFlying/facet/pull/15)
  is in actual implementation against independently approved schema r3. Values
  and 32-table STRICT/WAL initializer/session slices received independent review,
  including real SQL sealed-snapshot/NUL negative controls. Exact `56eaac6` passed
  450 full offline tests and [3.12/3.13 CI](https://github.com/GhostFlying/facet/actions/runs/36987351921).
  The initial finite-repository candidate `bf0bf0b` was held for audit relationships
  and caught-error rollback defects; corrected `e3eb14b` received independent
  acceptance and exact CI. Subsequent independently accepted/exact-CI slices are
  epochs `397282f`, History lifecycle `a6235f8`, events `a4cf745`, reviewed r4
  private getters/poll revision `07b452c`, expansion epoch work `d7874f3`, and
  History origin-epoch work `0fb0f10`. Known holds were corrected, not waived.
  Insert preparation/dispatch `32c4c66`, recovery claim allocation `f5279c7`, bounded
  SQLite WAL snapshot `c589b4c`, own-child SIGKILL tests `bb27213`, actual result/
  recovery-work recording `d1a89d8`, fact-only target audit `d2fb6a1`, and SQLite
  row-stepping/caught-failure rollback `c03e62f` also received independent slice
  acceptance and exact Python 3.12/3.13 CI. That earlier SQL snapshot passed
  879 full offline tests; [exact CI](https://github.com/GhostFlying/facet/actions/runs/37000255749)
  succeeded. These are storage-library facts, not Gmail invocation/fidelity or
  scheduler acceptance. SIGKILL is not physical power loss; a DB snapshot is not
  a complete credential/config bundle or migration receipt. Typed sessions are not
  real process locks; fresh-owner publication belongs to M1-03's reviewed extension.
  A real DB-21 probe found that `mode=ro` followed by the current supplied-connection
  view adapter created WAL/SHM for a clean stopped database. This is a retained
  historical failure, superseded for the finite library by independently accepted
  exact `16bcd0b99bf1118924b214bf9ded3976813f5e1a`: 1188 full offline tests and
  8 ownership controls passed; the prior d6 single-owner finding was closed by
  reviewed source before the model-policy change.
  [Exact CI](https://github.com/GhostFlying/facet/actions/runs/37014341329) passed
  Python 3.12/3.13. Production provider/runtime registries remain empty: actual
  managed-read/RV11, action consumers, migration/restore and whole DB-01..28 are
  incomplete.
  No immutable-live shortcut or sidecar repair is enabled. PR #15 stays Draft/open
  and unmerged. Later bounded action/policy persistence source
  `62d75c0253a6d66710a9d4d4a4b4346b8b55c6db` passed 164 AP/1352 full tests,
  installed-wheel checks and
  [exact CI](https://github.com/GhostFlying/facet/actions/runs/37023546672), but
  independent acceptance placed it HOLD on two required findings. At that
  snapshot R1 correction and independently approved R2 plan60333e9 strategy were
  released for bounded repair, not accepted corrected source. Later R3 and
  combined acceptance are recorded in the Oct3 handoff below; this historical
  HOLD is not relabelled. Production action/read registries remain empty; no
  actual M5 producer was enabled. The independently approved migration
  entry plan has SHA-256
  `2116d042a8065ba44b818eb7f832414e883cf7ebec27ba4c51ab4e3717746af4`;
  at that snapshot source still awaited accepted actual action input, qualified
  OS input, exact dependency CI and explicit root dispatch. The later finite
  release below is not a complete backup provider, migration/restore
  implementation or whole-package acceptance.
- M1-03 [Issue #13](https://github.com/GhostFlying/facet/issues/13) has an approved
  implementation plan and independently approved r3 wire/command-storage design,
  and a separately independently approved bounded OS root/lock plan. Root released
  that finite source slice against main `ff77e63` after the qualified SQL library
  and exact CI above. The policy pause ended after PR #19 integration. Historical
  OS `183dc6d` independently remains HOLD despite green CI: ordering failed across
  two opaque handles for the same physical root. The reviewed C1 terminal-metadata
  refinement was independently approved before code at full-plan SHA-256
  `4b7895159612699a05f7278652e9c45c884a914478ff61490a63f3358dcc898f`.
  Corrected `ea80db286fe110a69450076581b0b25810dcaf91` received nonauthor Sol
  acceptance: 123 focused/731 full offline tests, paired actual kernel/descriptor
  ordering and 256-cycle live/terminal controls, fork/Thread/uncertain-close checks,
  fresh noneditable-wheel/privacy/import controls passed. R1/C1 are resolved at
  this exact source, not waived for the historical candidate.
  [Candidate CI](https://github.com/GhostFlying/facet/actions/runs/37025751696)
  passed Python 3.12/3.13. [PR #20](https://github.com/GhostFlying/facet/pull/20)
  actually merged at that exact SHA via authorized normal fast-forward; no force,
  bot merge commit or settings change.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/37026826339) also
  succeeded on Python 3.12/3.13 at that exact SHA. Only low-level Linux
  root/owner/view/key resources are integrated: actual managed provider, actor,
  bootstrap/receipts, storage/credential participants and second real daemon
  refusal remain pending. Arbitrary mounts, NFS/SMB and native descriptor/fork
  paths outside the declared discipline are not qualified. M1-06 r2, M2-01 r2
  and M6-01 r2 designs
  are also independently approved preparation only, not implemented consumers or
  permission to skip their dependencies. Production authentication remains
  metadata/rule admission is now the active contract; controlled live Gmail
  verification remains separately authorized.
- M1-05 [Issue #14](https://github.com/GhostFlying/facet/issues/14) / [PR #16](https://github.com/GhostFlying/facet/pull/16)
  early pure-model/catalogue/serializer/logging unit received independent source
  acceptance at `c455f71ae63fa435c9bb02b82767aff4a032c30c`. Local verification passed
  488 full offline tests (including 33 logging subprocess cases), Ruff, CLI and
  installed-wheel export/privacy smoke; [exact source CI](https://github.com/GhostFlying/facet/actions/runs/36989013627)
  passed Python 3.12/3.13. The two-doc handoff also received independent affected
  review at `f209fbe616dc65c70bbcdc4a104cf82b0d5dad27`, which actually merged via
  normal fast-forward. [Main CI](https://github.com/GhostFlying/facet/actions/runs/36989986570)
  succeeded at the same SHA. The full package stays open for actual consumers.
- M1-04 [Issue #17](https://github.com/GhostFlying/facet/issues/17) /
  [PR #18](https://github.com/GhostFlying/facet/pull/18) early pure source
  `b94b610aec070617a4bd3c1249b58437cc9bfbae` received independent implementation/
  acceptance review; 120 OP cases/608 full tests, Ruff, both CLI help entries,
  installed-wheel privacy/export checks and
  [exact CI](https://github.com/GhostFlying/facet/actions/runs/37000045729) passed.
  Its coherent docs/head candidate received independent review and actually merged
  exact `ff77e63a823dc8bcb130836243746c067778b94f`;
  [main CI](https://github.com/GhostFlying/facet/actions/runs/37001014793) succeeded
  on Python 3.12/3.13. No file/network/OAuth/profile/token publication or full
  binding gate was exercised. Issue #17 stays open; SQL remains unmerged.
- Prospective model-policy [PR #19](https://github.com/GhostFlying/facet/pull/19)
  actually merged exact `a57dd77116ea79b44c177d03bb6b9815a5913795` after independent
  nonauthor source acceptance and candidate CI.
  [Main CI](https://github.com/GhostFlying/facet/actions/runs/37018290223) succeeded
  on Python 3.12/3.13. The temporary OS pause was an ownership handoff, not
  cancellation. At that handoff `m103_os_source` retained OS source and sole
  shared-status/integration ownership; `phase1_sol_policy_review` owned bounded
  SQL corrections and migration plan-only work and independently reviewed OS
  source it did not author. `phase1_os_acceptance_sol` independently reviewed
  SQL source and approved the C1 OS and bounded status-handoff plan. Current
  ownership transfers are recorded below. Historical model attribution,
  package dependencies, external authority and milestone gates are unchanged.

## Oct3 source and main-health handoff

- The [PR #21](https://github.com/GhostFlying/facet/pull/21) status snapshot actually
  merged exact `36b5a303856f00876c697f712ee98c9012c497c7`. Its
  [main CI37028856572](https://github.com/GhostFlying/facet/actions/runs/37028856572)
  failed on Python 3.12 while Python 3.13 passed: OL07 assumed 64 sequential
  Threads would reuse a retired Python thread ID. This is retained failure
  evidence, not observed runtime ownership bypass. The first harness candidate
  `a410ca1dab1e0f0a8980f77d0443f88a92e7b982` separately received independent H1
  HOLD despite full/CI success: legitimate sibling activity changed ancestor
  directory metadata included in its test oracle. Neither finding is waived.
- Corrected [PR #22](https://github.com/GhostFlying/facet/pull/22) actually merged
  exact `befe278285cfbd77798ffa58e8ef5d35b12e203a` at 2026-10-02T16:59:36Z after
  independent nonauthor acceptance, concurrent 150 focused/758 full tests,
  twenty complete nine-scenario child batches, real sibling-positive and
  descriptor/invalid-phase negatives, and fresh installed-wheel controls.
  [Candidate CI37036616826](https://github.com/GhostFlying/facet/actions/runs/37036616826)
  and [main CI37037683010](https://github.com/GhostFlying/facet/actions/runs/37037683010)
  succeeded on both Python jobs. Actual main logs show CPython 3.12.3 and 3.13.16,
  758 full tests and 40 CLI smoke tests each. All production OS and complete
  approved OS/C1-plan bytes remain the qualified `ea80db2` input; only bounded
  test-harness/main-health evidence changed, not runtime/provider qualification.
- SQL `2466834f79c41dbbf95e2919072ea9f57f36e7cc` remains historical R3 HOLD for
  foreign UoW exit invalidating the genuine creator lifecycle. Corrected
  `c0bb4b02277942f335ce278d359b60c16a46fd48` received independent acceptance with
  1598 full/73 R3-focused tests, eight actual WAL controls, installed-wheel
  checks and [CI37032060497](https://github.com/GhostFlying/facet/actions/runs/37032060497)
  both-success. Its actual ACTION plan is 546 lines with unchanged full hash;
  the earlier review's 535-line description was a clerical count error, not
  different source or retrospective acceptance of either held candidate.
- Normal combined carry `a9c4e36de6ad70294002a83e678a2a7cf1b012d6`, parents c0bb
  then befe, now has independent nonauthor combined acceptance: 1625 full tests,
  73 R3-focused/150 OS-focused/eight actual WAL controls, byte-preserved SQL/
  OS/harness inputs and fresh noneditable wheel. Author full 1625 also passed.
  [Fresh CI37038807962](https://github.com/GhostFlying/facet/actions/runs/37038807962)
  succeeded on both jobs. Actual checkout logs identify PR merge commit
  `8e703daf8a8739411324457dec98cc34c0dff036`, whose tree
  `b33a7679c0ed4e3f2cc6885d084ac3c0eb479cab` exactly equals candidate a9c's tree;
  run head metadata alone is not the tested-revision proof.
  [PR #15](https://github.com/GhostFlying/facet/pull/15) remains Draft/open/unmerged.
  This docs branch remains based on accepted main befe, not that SQL branch.
- Root explicitly transferred the approved migration plan/tree and released its
  finite source allocation to `m103_os_source`; source work starts only after
  this docs freeze/CI start.
  The preserved 217-line plan is SHA-256
  `2116d042a8065ba44b818eb7f832414e883cf7ebec27ba4c51ab4e3717746af4` and the
  232-line design is `3a9fedfcb3cf2fbaa410c982383fd459d8f1f1b73f58992e96883c9ad50042cf`.
  Source implementation/independent acceptance/CI are not yet complete. The
  approved 229-line restore-fence plan hash
  `1cee159f355ef6df39ec781cc75cf31ad43e26966c47d9c34ad306dd7c29c0ba`
  and 307-line design hash
  `3e8bd09eb9d6068d29d2e1bdf2eba617dcc20be695a65ba8b38f2e26f70aadf8`
  remain plan-only without source release. Neither supplies a complete
  config/binding/credential bundle, installation/provenance issuer or restore
  recovery/clearance consumer.
- `phase1_sol_policy_review` separately owns the source-released no-state
  read-bootstrap foundation under approved 217-line plan SHA-256
  `87321fe4ae703356a7aee8eb8c2f4a80a372f3bfc2ef8ba86c27e1c142029094` and preserved
  229-line design `9d28e18cee3dbaed00c939838686a6b715cefb569c268a4f3e73a0d1cc6c660e`.
  Its bounded launcher/latch/in-memory probe allocation is not accepted source,
  a state opener, managed-read producer, qualified runtime, daemon or RV11.
  Shipping action/read-provider/runtime inventories remain empty. Source
  authors do not approve their own design or implementation; root dispatches
  exact independent acceptance and separate integration gates.

`m103_os_source` remains the sole shared-status/integration writer. This separate
three-document handoff needs its own exact-source nonauthor review and fresh CI
before root-qualified integration. Whole M1-02/M1-03, actual M5 consumers,
credential ownership, complete backup/restore/migration, full maintenance CLI,
G1-G6, live Gmail, Dashboard and Compose remain incomplete.

## Historical planning and bootstrap record

The following records describe their then-current candidates. Current approvals,
engineering integration and remaining gates are in the sections above.

- Historical planning/normalization records below retain their original SHA/
  verification scope. Their then-pending G0/Draft states were superseded by the
  explicit approval and actual integration recorded above, not retroactively
  relabelled as approval or runtime proof.
- User authorized product-first reordering of the total plan, not G0 approval:
  goals → operating loop → overall acceptance → scope/non-goals → milestones →
  work packages/execution. Eight acceptance groups summarize existing contracts;
  the 36 card bodies, DAG, waves, CLI ownership and authority ledger are preserved.
  The file-based reordering plan received independent Astra high approval before
  editing. Exact candidate review and CI belong to this revision and are tracked
  in [draft PR #2](https://github.com/GhostFlying/facet/pull/2); earlier approvals
  do not imply approval of the new overview. No production work has started.
- [Repository bootstrap](implementation-plans/repository-bootstrap.md).
- User requested a complete maintenance CLI and atomic English commit subjects
  (`feat: impl ...`, `fix: fix ...`, other types with action verbs), plus one-time
  main-history normalization. [CLI specification](cli-spec.md) now covers full
  command families, offline/Compose maintenance and CLI-01 through CLI-08 gates.
  Stable request keys before submission, explicit preview producers and coordinated
  DB/credential ownership address preliminary review feedback. This substantive
  extension received its own independent Astra high technical approval at
  `eca99118b46db765960c7439246b6a1c5f4e5ccb`; preliminary findings were closed.
  [History normalization](implementation-plans/commit-history-normalization.md)
  was separately reviewed, executed and independently accepted. The reviewed
  CLI candidate maps to `5d623f201b4e4f8c701b196d3f017bf874f3e79a` with an
  identical tree, identity and original dates; this traceability does not extend
  the old `7c68991` review to the substantive CLI changes.
- [Phase 1 planning record](implementation-plans/phase-1-planning.md),
  [complete execution plan](phase-1-execution-plan.md), and
  [agent workflow](agent-workflow.md). [Epic #1](https://github.com/GhostFlying/facet/issues/1)
  tracks this planning unit and later ready work-package Issues. The planning
  worktree is isolated. Local document links/fences/headings, whitespace, private
  host-path checks, 36-package dependency references/acyclicity and staged-index
  repository safety passed for the initial candidate. Independent review of
  `a8e87de` requested changes. Independent technical re-review approved
  `7c68991ef5f47ba65cc61a0dcc2dfd80fdb0ca46`, closing R1-R3 and C1; 36-package
  uniqueness/missing-node/cycle checks and manual wave review passed. Prior
  [draft PR CI at `af3b793`](https://github.com/GhostFlying/facet/actions/runs/36960852657)
  passed Python 3.11/3.12; it does not cover this new CLI extension. The new
  CLI candidate received separate review and
  [new candidate CI at `5d623f2`](https://github.com/GhostFlying/facet/actions/runs/36965268013)
  passed Python 3.11/3.12. At that planning handoff G0 remained pending. These runs
  validate their exact candidate SHAs, not a later report-only commit. The
  [review record](reviews/phase-1-plan-review.md) preserves historical and current verdicts and
  responses. No
  production package, daemon, Gmail request, deployment, or image is
  introduced by this unit.
- This planning unit's locked local baseline passed on Python 3.13.5: environment
  sync, Ruff lint/format (31 files), 24 offline tests and spike CLI help. These
  checks preserve the existing spike baseline; they do not validate planned
  production behavior. No mailbox credentials or live Gmail calls were used.
- On 2026-10-02 the user authorized delegated Phase 1 work, multiple worktrees,
  Issue/PR tracking, atomic commits, Astra high / 6.1 Sol xhigh as needed, and
  root coordination/reporting only. Complex plans need independent review before
  implementation, then independent implementation and acceptance review.
- The user also authorized autonomous merges of engineering/work-package plan
  PRs inside the approved phase after those review and CI gates, and public
  `ghcr.io/ghostflying/facet` main full-SHA image publication through Actions once
  the phase starts. They clarified that the overall Phase 1 plan itself needs
  their review and explicit approval; the draft planning PR must not merge
  beforehand, and technical review/CI cannot start implementation. PRs only
  build; formal version tags/GitHub
  Releases, live Gmail operations and host deployment are not included. No
  image has been built or published yet.
- Repository: [GhostFlying/facet](https://github.com/GhostFlying/facet), verified
  PUBLIC with default branch `main`; `origin` points to it. On 2026-10-02 the user
  explicitly requested public visibility and their account's GitHub noreply email.
- Local verification: 24 offline tests passed; Ruff lint/format, spike CLI help,
  shell syntax, tracked/staged safety scan, documentation links/fences, and staged
  whitespace checks passed. No live Gmail requests were used for this bootstrap.
- The first push was rejected by `GH007`. The unpublished root commit was
  replaced using the current configured user/noreply identity, without changing
  saved Git configuration or email privacy protection. GitHub confirmed both
  author and committer use the account's noreply identity and attribution is
  `GhostFlying`. The rejected old commit is not in public history.
- Initial published commit: `53ac21b`. Its [offline CI run](https://github.com/GhostFlying/facet/actions/runs/36955887359)
  completed successfully on both Python 3.11 and 3.12: 24 tests in each job,
  tracked-content safety baseline, locked install, lint, formatting, and CLI smoke.
- The user-requested one-time main-subject rewrite now maps that root to
  `34818fe9f5d2d7bcb30353939b146418b2d5a814` and old `9d8595d` to current
  `main` `2f78fdf69cba786d2568689b0d0566d827d4285a`. All six reconstructed
  commits passed independent tree/header/identity/date/topology acceptance;
  the base-to-plan diff is unchanged. Private local rollback refs are retained
  and were not published. [Fresh main CI](https://github.com/GhostFlying/facet/actions/runs/36965264011)
  passed Python 3.11/3.12. [PR #2](https://github.com/GhostFlying/facet/pull/2)
  was then Draft/unmerged with G0 pending; the later approval/integration is above.
  Complete mappings and rollback
  anchors are recorded in the history-normalization execution appendix.
- Published GitHub tree checked: source/tests/docs/configuration only; no private
  runtime directory or credential files. The baseline scan is not a substitute
  for the production privacy tests still required by later milestones.
- Runtime credentials/evidence are ignored local files. No live Gmail writes are
  part of this bootstrap, and no experimental state is adopted as production data.

## M2 runtime composition handoff (2026-10-04)

- The exact-SHA review of the first runtime candidate found and blocked two
  issues: the CLI was not actually dispatching the library seam, and invalid
  Google factory paths constructed an untyped `StorageFailure`. The revised
  plan now explicitly names this unit library runtime composition; `facet run
  --once` now dispatches the reviewed production runtime after local binding
  checks, while the default unknown-auth provider remains fail-closed.
- The follow-up candidate adds typed factory failures, access-token-only
  construction tests, and missing/swapped/expired/mismatched credential tests
  with unchanged bindings and no sync service on failure. The focused runtime
  and factory suite passes (36 tests including credential consumers); the
  complete offline suite passed 2490 tests, both CI lanes passed, and the
  candidate merged as `bc3922a908458ba0e8db1d1573773bfd22fe6dbd`. No live
  Gmail or deployment action was used.

## Current product closure

The bounded unit in `implementation-plans/cli-sync-closure.md` is accepted at
candidate `e2d38ef`. From a clean private state directory, the CLI can execute
`init`, fake authorization/profile binding for both roles, exact sender rule
creation, write-free backfill preview, explicit backfill start, and
`run --once --fake`. The first run discovers one synthetic thread, inserts and
reads back one message, and persists one mapping; a second process run produces
zero new projections. The subprocess evidence is in
`tests/cli/test_bootstrap.py`; the focused closure/credential/command-operation
tests passed 67 cases and the complete offline suite passed 2495 tests.

The candidate also validates request-key replay and cross-command conflicts,
including atomic start activation and restart recovery. Rule replay currently
uses deterministic rule identity rather than a separate operation row and
payload digest; that is a documented P2 follow-up, not evidence for the full
CLI contract.

This is implemented and offline-tested, not live-Gmail-verified or Phase 1
complete. The follow-up OAuth binding unit at candidate `723c9cf` adds the
production role-specific loopback authorization path with TTY-only URL output,
actual-grant scopes, profile/account verification, and durable role publication.
The candidate received independent approval; its focused tests passed 73 cases
and the complete offline suite passed 2501 tests. No live OAuth/Gmail evidence
  is claimed. The fake runner exercises metadata/rule admission; controlled
  Gmail verification remains a separately authorized external gate. Dashboard,
  Compose, Actions, scheduling and remaining maintenance commands
remain outside these closure units.

## Production CLI sync-path wiring handoff (2026-10-04)

The production command seam is integrated in PR #53 at merge
`727e1d99c174019b0c432653e2e274b2f10743b7`; its implementation plan is under
`docs/implementation-plans/production-cli-sync-path.md`. After both role
bindings are verified, non-fake `backfill start` uses the Google Gmail service
factory to obtain the source profile fence and persist H0/epoch. Non-fake
`run --once` verifies both profiles/scopes, loads the persisted ruleset, and
dispatches `ForegroundSync` through the reviewed production composition. The
receipt exposes aggregate counts only.

The current production path performs metadata/rule admission without a
source-auth provider, raw fetch for admission, or DNS lookup. No Gmail network
call, OAuth exchange, target write, deployment, or release was performed by
this unit. Focused CLI/runtime tests and the complete offline suite (2512
tests) passed, as did Ruff/format and repository safety. This is
implemented/offline-verified only; a controlled live Gmail run remains a
separately authorized external gate.

## Product-first recovery correction (2026-10-06)

The bounded correction in `implementation-plans/critical-path-simplification.md`
is implemented locally and offline-verified. The foreground path now resumes a
persisted History poll through the real owner transaction after a typed
provider failure; Gmail system-label changes are filtered before business-event
creation; untracked message deletions are consumed without false attention;
and typed provider failures remain retryable while unexpected programming
failures are no longer converted into permanent attention. The post-dispatch
unknown-insert recovery path is unchanged.

Focused sync/history/action tests passed 109 cases and the complete offline
suite passed 2645 tests. This remains synthetic/offline evidence only: no live
Gmail, OAuth, deployment or target mutation was performed. Removal of unused
bootstrap/launcher modules and broader exception-taxonomy cleanup are deferred;
the next product gate is controlled live Gmail sync after this unit is
committed and reviewed under the existing authorization boundary.

The local Compose runtime was then exercised with the candidate source under
the image's non-root UID, read-only root filesystem, and persistent state
volume. `init`, fake authorization, sender-rule publication, preview, explicit
backfill start, and two `run --once --fake` invocations completed; the first
reported one projection and the second reported zero new projections with no
attention. The official Dockerfile rebuild itself was attempted but Docker Hub
timed out before fetching the pinned base; the runtime check therefore used a
cached local diagnostic base with only the committed source overlaid and is not
an image-publication or Dockerfile-build claim.

That build limitation is now resolved for this candidate: Tailscale SSH to
sgbox allowed the unchanged Dockerfile to build against its pinned base digest
and locked dependencies. The image was streamed back with `docker save/load`
and verified locally as
`sha256:9cf1757ae273353ab860fb33551f2e2375fc19e7e30ed82336c5c56ac81ce086`.
The same Compose command path passed again using this freshly built image and
a separate synthetic volume: first run projected one, second run projected
zero, both with zero attention. The stopped DB confirmed one mapping and one
verified insert attempt; image source and lockfile checksums match the local
candidate. This is a local Dockerfile/Compose acceptance, not GHCR publication,
multi-architecture acceptance, deployment to real state, or live Gmail evidence.

## Historical next-unit note (superseded)

This old note proposed a source-Gmail-path evidence producer; the 2026-10-05
user decision superseded it. The current product-bearing work is the smallest
integration that exercises metadata/rule discovery through the existing
adapter, action/repository and BackfillProducer owners. Ordinary phase-internal
plans/engineering PRs advance under the approved autonomous gates; material
product/privacy/authority changes return to the user. The complete M1/M2
foundations and their remaining runtime/provider consumers remain open. M1's
minimum scope is:

1. Establish the production Python package/CLI without breaking the spike.
2. Validate configuration and explicit source/target bindings; refuse identity
   swaps or identical accounts, and separate private internal configuration from
   allowlisted public diagnostics.
3. Implement schema v1, migrations, durable repositories, process/writer locks,
   rule effective times, and metadata-only typed payloads.
4. Establish private OAuth/token handling and synthetic tests; require separate
   authorization for real account setup or additional scopes.
5. Define Dashboard response models and privacy sentinels before exposing HTTP.
6. Keep Gmail authentication/classification provider-owned; test that
   authentication headers do not become a Facet admission gate.

Production live copying, bulk backfill and deployment require their recorded
scope/target decisions. Dependency-ready offline engineering can proceed while
an external gate remains pending; keep final milestone gates in order and record
actual verification scope instead of marking a partial gate complete.

## Known limits and decisions still needed

- Gmail insert is not exactly once; target search timing is not an SLA. Production
  crash/recovery and ambiguous-ID tests remain necessary.
- Default raw processing is memory-only with no disk spool; source loss may
  prevent recovery. DB contains only necessary metadata and state.
- Production target must be newly created and dedicated, with operator
  attestation/configuration that Facet is the only application writer before
  OAuth. After target OAuth, read-only account/content checks must cover normal
  mail, drafts, Spam, and Trash before the first projection/insert. Unexpected
  or unmanaged content/account mismatch blocks deployment and new projection
  writes; report-only, no delete, claim, cleanup, or automatic migration. Gmail
  metadata/OAuth cannot prove sole-writer status. Existing deployments retain
  mappings/jobs/audit and remain blocked until the prerequisite is checked;
  this docs-only change does not implement runtime enforcement or prove live
  acceptance. See [product contract](product-contract.md).
- AI connector retrieval is an AI-product responsibility, not a Facet gate.
- Real bank domains, live account/test scope,
  dogfood host/local volume/Nginx entry, license and formal version release remain
  undecided. GHCR/package public visibility, main full-SHA publication, public
  anonymous pulling, and the first multi-arch artifact are verified above;
  source publication does not substitute for deployment or live-sync checks.
- Authentication trust, unknown-insert attribution (excluding old unmanaged/spike
  copies), and daemon/CLI single-writer coordination are required early ADRs.
  Unique fingerprint matches alone do not establish this insert's provenance.
- Overall Phase 1 G0 is approved at the exact reviewed SHA; production milestone
  completion is not implied. Internal merge/GHCR scope does not authorize new
  live Gmail or host actions. Final milestone live
  gates remain separate from dependency-ready offline engineering outputs.
