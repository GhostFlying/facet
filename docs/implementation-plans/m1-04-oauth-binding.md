# M1-04: OAuth, account binding and credential ownership plan

Date: 2026-10-02. Revision: r1. State: plan_drafting; not implementation approval.

Owner: delegated `phase1_architecture_plan` (Astra high); independent reviewer
must not be this plan/credential ADR's author. Root coordinates dispatch and
acceptance. Parent: [Phase 1 Epic #1](https://github.com/GhostFlying/facet/issues/1).
Canonical package: [M1-04](../phase-1-execution-plan.md).

Owned worktree: sibling `facet-worktrees/m1-04-oauth-binding`.
Branch: `docs/m1-04-oauth-binding-plan`.
Starting/actual plan base: `c18bfbee09b985ee7b9bb5c230ee2a70427c7edc`.
PR #10 is actually merged at this SHA; root verified post-merge CI 36978909460.
This incorporates P1-02 provider/helper output, not its still-pending CT slice.
G0 approval remains `caba7c73895a303d329cf3eba1c89557530c38c5`.

Current dispatch permits this plan only, plus one tracking Issue if necessary.
No source, token files, ADR implementation, commit, push, PR, Google API call,
OAuth interaction or ignored spike state is authorized by this dispatch. If the
M1-01 merge makes P1-02 CT ready and root dispatches it, pause this drafting lane
and complete CT first. Review binds the exact plan hash, not just its filename.

## Outcome and evidence boundaries

Deliver production `gmail auth/reauth <source|target> --port <port>` and offline
`gmail auth-status`, immutable account-role binding checks, a private per-role
credential manager, atomic token replacement and serialized refresh. Reauth
retains jobs, mapping/intent history, stopped generations and approved scopes.
Every startup verifies both live profiles before enabling new Gmail writes.

Default source scope is `gmail.readonly`; target is `gmail.insert` plus
`gmail.readonly`. Gmail OAuth authorizes mailbox-level access; it does not itself
enforce sender/thread disclosure selection. Successful OAuth or profile checks
never authorize backfill, insert, label writes or automatic sender admission.

M1-04's offline engineering gate is separate from G1 integration and D3/G6 live
OAuth/re-auth evidence. Fake token exchange and profiles prove code behavior,
not Google consent, account ownership or live refresh longevity. No token-file
existence, expiry estimate or historical successful refresh means currently
healthy authorization. No changes to the spike or imports from its runtime.

## Inputs, sequencing and interface ownership

Read AGENTS and the ordered status/product/project/Gmail/Dashboard/CLI/execution/
workflow/progress documents before implementation. Current shared status files
are historical snapshots; actual Issue/PR/review/main evidence determines input
readiness. Read only tracked spike source/results as reference, never private
`.facet-spike` files.

| Input | Status at this plan base | Required closure before consumption |
| --- | --- | --- |
| `p1-core-v1`, `p1-writer-v1` | Independently reviewed and integrated at `09031e723af1ef6590dc6746744ee52894501e38` | Preserve their owner/view/role-lock hierarchy, restore fence and finite shared inventory |
| M1-01 package/config/contracts | Implementation candidate; not yet actual reviewed/merged input | Record exact accepted SHA; import canonical Role/SourceMode/BindingState/Revision/ErrorCode, never copy enums |
| P1-02 | Provider/helpers merged at c18; CT01-04 pending | Full package integration before dependent persistence implementation; use only reviewed real helpers |
| M1-02 schema/repositories | Plan/extension work; no frozen executable binding repository | Align exact reviewed schema extension and repository signatures; no local SQL or shadow Binding record |
| M1-03 writer/read-view/bootstrap | Not implemented | Its owner capability, stable request/receipt, manager lifecycle, view provider and command-registration extension must be reviewed before real CLI integration |
| M1-05 output/logging | Later owner | Reuse M1-01 CLI envelope; contribute closed auth projections/error mappings for independent M1-05 integration; no substitute public DTO framework |
| M2-01 worker transports | Later owner | Consume manager's reviewed snapshot/refresh interface later; M1-04 does not invent the full Gmail adapter protocol |
| M6-01/02/03 | Later owners | Consume credential inventory/revision validation and existing locks; complete bundle backup/restore and container verification remain their gates |

Design can proceed now. After plan approval, root may dispatch a documentation
ADR slice defining `m1-credential-v1` in
`adrs/oauth-credential-manager.md`. That ADR gets independent review before
credential implementation. It is distinct from M1-06's `authentication-trust.md`:
OAuth identity is not proof of message sender authenticity. No AUTH accept branch
is enabled here.

Before source implementation, record actual M1-01/M1-02 dependency SHAs, review
carry-forward and credential ADR version. M1-03 may implement in parallel only
after both owners independently review the exact integration seams; do not call
an unimplemented lock, receipt or repository a usable input. Real auth CLI and
startup acceptance must wait for M1-03 integrated code. No circular requirement
on future M2-01 or M6: unit tests inject bounded token/profile exchanges; M1-04
tests credential participation in the current ownership protocol, not a replica
of future whole-bundle restore. Later integration owners run those real E2Es.

### Planned file boundaries

Only this file is writable in the current dispatch. Future dispatch, after the
relevant reviews/dependencies, would assign these focused files:

| Owner scope | Purpose |
| --- | --- |
| This plan and `docs/implementation-plans/adrs/oauth-credential-manager.md` | Credential/scopes/exchange/revision contract and crash table |
| `src/facet/gmail/oauth.py`, `credentials.py`, `binding.py`, `loopback.py` | Flow adapter, single manager, profile comparison and one-shot local callback |
| `src/facet/gmail/private_files.py` | Credential-specific bounded/no-follow atomic envelope I/O; consumes shared M1-03 root/ownership checks, does not create alternate locks |
| `src/facet/cli/auth.py` | Actual stopped-owner auth/reauth and read-view auth-status handlers |
| `tests/unit/test_oauth_*.py`, `test_credential_*.py`, `test_binding_*.py` | Synthetic library exchange, scope evidence, profile and file/refresh tests |
| `tests/cli/test_auth_*.py` | Real CLI subprocess/PTY/loopback, request replay and ownership/privacy behavior |
| `tests/integration/test_credential_ownership.py` | Offline actual multi-process owner/maintenance contention and crash tests, never automatic live Gmail |
| `docs/oauth.md` | Supported local/SSH preparation, safe failures and explicit live/container limitations |

The Gmail package initializer and CLI registry are shared integration seams:
request root's single-file ownership handoff, not concurrent edits. M1-02 alone
owns DB schema/repository files; M1-03 owns runtime/locks/command wire; M1-05 owns
global errors/logging/public DTOs. No `src/facet/contracts/` changes without its
owner's reviewed extension. No current pyproject/lock/workflow changes; if a new
dependency proves necessary, update plan and obtain package-owner dispatch.
Root delegates shared status/README/progress updates to the integration owner.

## Credential ADR: choices that must be closed before code

The ADR must supply exact named records, field types, required nullable fields,
closed variants, bounds and executable owner. It cannot merely label a record
"typed". This plan selects the following approach; its complete field-level
extension and crash proof are the next independently reviewed design artifact.

1. A v1 credential envelope is private, manager-owned, and distinct from DB and
   command payloads. It binds role, projection/state lineage, immutable binding
   revision, credential revision, approved scope-policy revision, proven grant
   evidence and a closed allowlist of provider token fields. Reject duplicate or
   unknown keys, unsupported versions, oversized strings/files and invalid times.
   Tokens/client secrets are never shared domain records. Do not save arbitrary
   token responses or blindly persist every field in `Credentials.to_json()`.
2. Use two fixed per-role token paths beneath the verified private state root;
   no path selection from role input or token-provided endpoints. Parent
   directories are 0700 and credential files 0600, owned by service UID.
   Reject symlink/path traversal, unsafe existing ownership/mode and unexpected
   object types; do not repair arbitrary paths with chmod or overwrite them.
3. Replacement uses same-directory exclusively-created 0600 temporary file,
   complete write, file fsync, atomic replace and directory fsync. Cache
   publication occurs only after the selected durable metadata handoff. A temp
   token file is an authorized private credential artifact, not a mail spool;
   interrupted temp-file handling is bounded to known manager-owned files.
4. DB and token file are not atomically committed together. The ADR must choose
   an exact metadata-only prepare/finalize protocol with old/new revisions and
   operation identity, aligned to M1-02's reviewed repositories. All boundaries
   (prepare, temp sync, replace, directory sync, metadata CAS, cache publication,
   receipt completion) get a restart table. A mismatched or unacknowledged
   revision cannot serve new credential snapshots. No guessed commit, blind
   rollback to potentially revoked tokens, empty DB or success receipt on failure.
   Wrong profile/scope before replacement leaves the prior accepted file/binding
   intact. After ambiguous persistence failure, preserve diagnostic metadata and
   fail closed until the reviewed recovery path reconciles exact revisions.
5. Immutable in-memory snapshots expose only required access-token/expiry and
   role/revision metadata to an owned caller; no refresh token/file writer escapes
   to a worker. Snapshot repr/str and errors are sealed. Python memory is not
   claimed securely erased; release references and avoid copies where possible.
6. Define minimal auth exchange and profile-verification seams locally to this
   package, with exact allowlisted outputs; no `ProviderResult`, full adapter,
   business-state fake, generic JSON error or trustworthy-authentication oracle.

### Scope evidence and binding

Maintain distinct requested/approved, actually granted, and required-for-mode
scope sets. A constructor populated with desired scopes, `has_scopes()` alone,
successful `getProfile` or config mode is not actual-scope evidence. The ADR
records grant evidence provenance from successful OAuth exchange/refresh;
omitted scope response is handled only under the precise OAuth semantics and
previous validated grant lineage, never by filling unknown imported credentials
with the config's desired set. Insufficient/unknown/unapproved grants fail closed.

Source readonly never requests modify/send/settings/full-mail scope. Source
convenience and target label-creation grants require explicit separately reviewed
mode/scope selection and user approval; default auth and reauth cannot widen them.
An existing broader consent grant does not itself enable broader Facet actions.
Freeze how approved supersets versus unapproved excess grants are classified
before code; reject unapproved excess rather than silently adopt it. No token
revocation or cloud-project change is performed automatically.

The only identity probe here is bounded `users.getProfile(userId="me")`, with
field selection/minimal extraction. Its emailAddress is compared using the
reviewed config/binding normalization, not Gmail dot/plus alias guesses.
No People/settings/userinfo/email/OpenID scope is added for identity. Check each
role against configured and persisted identity and check source differs from
target. Swapped token files, same live account, changed address, wrong lineage,
wrong role or binding revision is refusal, not rebind. Count/history fields in
the profile are discarded here and cannot initialize checkpoints or mappings.

Fresh startup verification of both roles precedes writes; neither valid role
alone makes the projection ready. Transient auth/network failure keeps local
diagnostics usable and jobs intact. Successful reauth/verification does not clear
restore revalidation, daemon pause, stopped generations or unknown insert states.
Target unmanaged-mail reporting remains M1-06; this package does not list mail.

### One-shot Desktop flow and CLI receipt

Use the existing locked Google OAuth library for OAuth primitives, with explicit
PKCE S256 and unpredictable state. Select a thin local callback adapter rather
than unmodified `InstalledAppFlow.run_local_server`: its current helper prints
and logs the auth URL, and logs callback requests. Do not monkeypatch global
stdout or weaken TLS/OAuth checks. The ADR defines exact library calls and tests
them against the installed lock revision before implementation.

Bind numeric `127.0.0.1` on the explicitly selected available port before showing
the URL; exact redirect URI, bounded listener/token/profile deadlines and cleanup
on every exit. Validate callback method/path/Host, bounded query size and unique
state/code/error fields; compare expected state, reject malformed/duplicate/wrong
callbacks without exchanging an attacker-supplied code. PKCE verifier/state/code
stay memory-only. No OOB/manual code paste, device flow, embedded browser, Web
Dashboard OAuth route, arbitrary redirect URL, arbitrary token endpoint or
non-loopback listen fallback. Return only static no-store callback text without
reflecting query values, IDs, token, account or provider error. Browser callback
receipt is not a promise that account validation and persistence completed.

Use an explicitly opened controlling terminal for the one-time URL, only during
interactive auth; stdout `--json` remains exactly one result document, stderr
remains fixed codes. No controlling terminal means controlled authorization
required before network or credential replacement, even with `--yes`. Do not
print the URL to redirected logs or ask for tokens in chat. SSH same-port
forwarding is operator setup, never performed by the CLI. Local browser opening
must be explicit and cannot substitute for scope/role confirmation.

Auth requires initialized managed state and the M1-03 stopped owner; no bootstrap
credential shortcut. Register auth/reauth as A workflows with a stable client
request key established before acceptance. Durable record holds kind/role,
approved policy/reference revisions and controlled progress/result, never URL,
code, token or arbitrary client JSON. Same-key replay first looks up the existing
workflow: completed never repeats consent/replacement; pending after restart
uses the reviewed phase recovery/refusal, not automatic new OAuth. A new explicit
interactive attempt requires its own safely resolved request lifecycle. First
response loss remains discoverable by request key. Same key with changed role,
binding or semantic scope policy is a conflict. Freeze exact digest input and
phase/result fields jointly with the M1-03 registry owner before registering.

## Refresh and maintenance concurrency

Preserve `owner EX → view EX (bundle maintenance only) → source credential mutex
→ target credential mutex → short writer transaction`. Interactive auth owns
owner EX for the entire browser/network flow. No daemon or backup/restore can
cross it. Normal daemon refresh already holds process ownership and takes one
role mutex; never hold a DB transaction over network waits. Different roles may
refresh independently, same-role callers share one in-flight refresh result.

The manager releases its credential mutex before awaiting writer-actor updates;
updates carry revision/CAS. Writer never waits on refresh while holding a DB
transaction. A publication barrier prevents handing out a file/cache revision
before its matching metadata is durable, without reversing locks. Test the late
CAS/cache-update race explicitly. Worker libraries must not automatically refresh
their own copies; M2-01 integrates manager-mediated refresh and independent HTTP
transports without unconditional retry of Gmail writes.

Refresh uses bounded network deadlines and preserves a missing replacement
refresh token only under the existing verified credential lineage and upstream
semantics. Handle rotated token, reduced scopes, malformed success, timeout,
invalid_grant, access denial and client-policy failure separately with existing
controlled codes or an independently reviewed extension. No unfiltered exception,
provider response, scope string from an attacker, traceback or request URL is
logged. invalid_grant blocks the affected role and requests explicit reauth;
it does not delete queues, revoke tokens, widen scopes or launch a browser.

M6 backup/restore holds owner/view and both role locks, snapshots the envelope
with matching metadata revision, and rejects incomplete/mixed bundles. M1-04
provides bounded file inventory and validation, not its own backup engine.
Offline auth-status uses M1-03 read view and safe persisted metadata only: no
token loading through auto-refresh, no credential bytes in result. Last verified
time and expiry are separate from live health; absent/expired/unknown/stale must
stay distinguishable. Restored credentials require live binding revalidation
before use and do not clear the independent restored-effect fence.

## Verification plan

Tests use synthetic OAuth responses and addresses only. P1-02 network guard
denies external calls; PTY/loopback tests explicitly allow only their allocated
local listener. Child processes install their own guard. No test discovers
credentials from HOME, ADC, environment or spike directories. Negative controls
must fail the sentinel/ownership oracle before proving production behavior.

| ID | Required evidence |
| --- | --- |
| OA-01 | Exact default scopes for both roles; no send/delete/modify/settings scope or mailbox mutation; unsupported role/mode denied before I/O |
| OA-02 | Actual grant different from desired; partial/reduced/excess/unknown grant and omitted scope response with/without valid lineage; has_scopes/config alone cannot pass |
| OA-03 | Fake profile same-account, swapped roles, changed account, wrong envelope lineage/revision, malformed address rejected; prior accepted credentials/binding/jobs unchanged |
| OA-04 | Startup probes both roles, either failure prevents write readiness; reauth success leaves pause/stops/restore fence/unknown intents intact |
| OA-05 | State mismatch, duplicated query parameters, wrong path/Host, code+error, oversized callback, expired flow and PKCE verifier mismatch never commit token; no reflected content |
| OA-06 | Port occupied, absent terminal, browser cancellation, token timeout and profile timeout close listener/release ownership with controlled result; no empty/partial credentials |
| OA-07 | Real subprocess/PTY auth with synthetic exchange: explicit terminal URL only; stdout one JSON, stderr controlled; non-TTY request/confirmation guards and private/public refusal |
| OA-08 | Stable request key before flow; first-response loss, same-key replay/different payload, crash after replacement before receipt; no repeated completed OAuth/replacement |
| OA-09 | Actual files: 0700/0600 and service UID; symlinked parent/file, traversal, unsafe mode/owner/type, duplicate/unknown JSON fields/version/oversize refused |
| OA-10 | Inject write/fsync/replace/directory-fsync/DB-CAS failure at every credential commit boundary; preserve old accepted or explicit recovery state; no false completed receipt |
| OA-11 | Actual subprocess termination at durable boundaries plus restart validates exact old/new revisions; distinguish these from exception-only rollback tests |
| OA-12 | Concurrent same-role expiry has one serialized refresh; other role remains independent; rotated token and missing replacement token semantics tested; late stale update cannot overwrite new revision |
| OA-13 | Real owner-lock contention: daemon versus auth, two auth processes, auth versus stopped maintenance; bounded refusal/wait, no second writer or hidden daemon |
| OA-14 | Credential mutex/writer callbacks and publication barrier interleavings terminate without deadlock; real SQLite transaction probes show no network/terminal wait inside transaction |
| OA-15 | invalid_grant/401/partial-grant/policy/malformed responses map to fixed codes, jobs retained; offline auth-status/maintenance inspection still work with all network forbidden |
| OA-16 | Inject token/client-secret/code/state/auth-URL/provider-body markers into every failure; absent from DB/WAL/journal/receipt/client journal/log/stdout/stderr/public/private CLI; only exact manager-owned 0600 credential paths allow credential sentinels |
| OA-17 | Capture third-party loggers at DEBUG and HTTP callback request logs; sentinel negative controls; errors/repr/traceback paths never publish secrets; zero mail-content files anywhere |
| OA-18 | Offline read-view during credential replacement reports coherent/stale metadata rather than live health; backup participant requires exact revisions and cannot race auth/refresh; final real bundle restore E2E deferred explicitly to M6 |
| OA-19 | Spike entrypoint/tests unaffected; production startup/auth never probes or imports ignored spike files or ADC/default credentials; profile history does not seed H0 |
| OA-20 | Supported SSH/local loopback runbook and package command help match real handlers; container auth port/UID/mount recipe prepared, actual image/Compose proof remains M6-03/06 |

For OA-10/11 the reviewed ADR enumerates each persistence point and expected
restart result, including full disk and SQLite refusal. Tests must assert durable
state and call counts, not merely expected exception text. OAuth token files are
the only narrow credential persistence exception; mail content has none. Accepted
scope evidence/account bindings remain private metadata, not public strings.

Implementation baseline: locked sync, Ruff lint/format, full pytest, `facet` and
`facet-spike` help, repository safety, targeted auth subprocess/fault/privacy
tests. Local available test runtime is managed CPython 3.12.13 with SQLite 3.53.1,
validated for helper tests; it is not production-host/Compose/WAL acceptance.
Use an independent worktree venv and current accepted lock. CI matrix/version
comes from actual integrated M1-01, not assumptions based on this older base.

## Delivery slices, review and stop gates

1. Plan review: exact r1 hash/base, pending interface owners and authority scope.
2. Credential ADR authoring/review: close exact records, grant evidence, secure
   loopback/library boundary, file/DB/receipt restart table and lock proofs.
   M1-02 and M1-03 owners review interface alignment; independent Astra reviewer
   approves the design. Their not-yet-frozen APIs are not invented here.
3. After actual dependency integration and root dispatch: focused credential
   file/profile/scope/refresh implementation plus unit/fault tests; then actual
   stopped-owner CLI/startup/read-view integration and subprocess tests. Partial
   slices do not close M1-04 or G1; no help-only success or skipped pending tests.
4. Independent exact-candidate code/acceptance review and CI; normal atomic
   English user/noreply commits/push/PR only when dispatched. Root verifies and
   delegates integration, then M1-06 consumes offline capability for G1.
5. D3-authorized real OAuth/profile/re-auth later; M6 image/one-off/backup/restore
   and actual live invalidation/re-auth/pending-work continuation remain explicit
   separate evidence. No fake result closes those gates.

Stop before implementation for missing dependency/contract versions, unsolved
file/DB crash ambiguity, unsafe loopback/logging defaults, grant evidence inferred
only from configuration, an ownership cycle, or required changes outside file
scope. Submit technical issues to root; material privacy/product/authority
changes go to user. Do not silently weaken a gate. Failure never triggers token
revocation, target cleanup, new scopes, forced account binding or empty DB.

## D3 external decision packet (not yet requested/executed)

Root submits this only when usable reviewed tooling is ready, not as a blocker
to offline design. User supplies private account configuration locally and uses
the supported OAuth flow; no token or account identities are requested in chat
or posted to GitHub. The packet needs:

- Exact source/target roles and distinct approved accounts recorded privately;
  OAuth Desktop client/project selected by user; default scopes shown first.
- Explicit authorization for the interactive grant, bounded token/profile read
  checks and refresh test. No message list/raw/insert/labels are implied. Later
  selected-thread tests/backfill/repair need their own precise D3 scope.
- Explicit separate choice for convenience/label scopes if wanted; default is
  none. Consent-screen/project publication changes are not automatic.
- Operator/browser host and same-port SSH arrangement; no host firewall, system
  service or network changes by the CLI. M6 tests a stopped one-off container
  with the same state UID/mount and a documented loopback-safe helper arrangement;
  Linux host-network one-off is a candidate, not an authorized host action or
  a new public listener. M6 must verify reachability without binding public OAuth.
- Failure/exit plan preserves old accepted binding and jobs; reauth after actual
  revocation/expiry requires an explicitly selected role and user participation.
  No agent-initiated revoke is implied. Offline diagnostics remain available.

External Testing refresh-token lifetime and Workspace policies are limitations
to explain, not reasons to promise unattended permanent credentials or silently
change Cloud settings. D4 host/deployment and D8 monitoring remain separate.

## Read-only evidence used for design

Inspected tracked `src/facet_spike/oauth.py` only: it is reference code, not a
production privacy/ownership implementation. Lock at c18 contains
google-auth-oauthlib 1.5.0, google-auth 2.59.1, google-api-python-client 2.201.0,
oauthlib 4.0.0 and requests-oauthlib 2.0.0. Installed locked library source shows
the helper prints/logs its URL and routes callback request logging to a logger;
scope constructor arguments and grant evidence are separate. Recheck installed
versions after M1-01 integration; current online API docs can lag the lock.

Primary references checked 2026-10-02; these are protocol/library inputs, not
live account evidence:

- [Google installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app): Desktop loopback, PKCE/state and supported consent path; OOB is not a fallback.
- [Flow API](https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html): library boundary, supplemented by exact installed source inspection.
- [Google credential API](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.credentials.html): requested/granted scopes and mutable refresh state; implicit library refresh must not bypass the manager.
- [OAuth scope response semantics](https://www.rfc-editor.org/rfc/rfc6749#section-5.1): distinguish grant response evidence from local desired scope configuration.
- [Gmail scope catalog](https://developers.google.com/workspace/gmail/api/auth/scopes) and [getProfile](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile): minimal role grants and identity-only probe.
- [Google token expiration](https://developers.google.com/identity/protocols/oauth2#expiration): consent/project policy and token lifetime caveats; actual reauth remains a live gate.

No OAuth endpoint, Gmail account, ignored credential/mail file, mailbox write or
host configuration was used to produce this plan. No implementation tests are
claimed by this document; OA-01 through OA-20 are future required evidence.

## Execution appendix: credential ADR design dispatch

Date: 2026-10-02. Original approved r1 is preserved byte-for-byte as the first
28064 bytes (369 lines), SHA256
`fbc37240dd2fbeb920f835d15fb2456aceec9d15f73fb19072f6bbdfd07ac803`.
Independent reviewer phase1_plan_review approved that exact plan/base c18 with
no blocking finding. This is design eligibility, not source/live authorization.

After priority P1-02 CT delivery, root dispatched credential ADR authoring only.
The owned worktree remains at c18; M1-01 actual merged b1e is known but no
unapproved baseline/ref change or dependent source was made here. Written ADR:
[oauth-credential-manager.md](adrs/oauth-credential-manager.md), proposed
`m1-credential-v1` r1. It defines private finite records, exact scope provenance,
role/profile guards, one-shot PKCE/state callback and terminal/log boundaries,
single-flight role refresh, requesting/validated/committed metadata handshake,
file fsync/replace/DB publication and restart table, plus maintenance participation.

New authorization omitted-scope semantics do not require previous credentials;
refresh omission separately requires prior attested grant lineage. Neither uses
locally requested constructor scopes as proof. No sender-authentication accept
policy or insert-attribution behavior is introduced.

M1-02 schema and M1-03 wire/lifecycle/receipt protocols are pending reviewed owner
extensions, not executable interfaces invented by this ADR. Required storage,
owner and sealed-logging handshakes must be independently aligned before source
implementation; M1-05 integration does not authorize arbitrary log suppression
shortcuts or pretend public DTOs. M6 remains the real bundle/container owner.

Current writable scope is these two documents only. No source/SQL/tests, client
JSON, private credentials/mail, live API/OAuth/revocation, commit/push/PR or
deployment changes occurred. Whitespace/scope/manual privacy checks apply to
untracked drafts; tracked/staged safety alone cannot certify them. Exact full
file hashes and remaining inputs go to root for an independent ADR review.
The author cannot approve their own design. Any M1-02 schema-review dispatch
takes priority over continuing this lane, as does a P1-02 correction request.

### Credential ADR r2 design-review corrections

Root dispatched local correction of the independent r1 changes_requested result,
not source implementation. The owned branch normally fast-forwarded from c18 to
actual main `1b7cd58b4846aab86edcbb781a999abb968d047c`; root verified P1-02 CT
integration and post-merge CI 36982879970. The original plan prefix/base above is
historical and unchanged, not rewritten to imply earlier dependency completion.

Credential ADR r2 closes lost-candidate replacement for both first authorize
(accepted revision zero) and reauthorize (positive revision), with old-key replay,
candidate-first recovery, full predecessor CAS and atomic old/new receipt handoff.
Its new nullable supersedes_change_id is an exact owned metadata field, requiring
the M1-02/M1-03 reviewed extension before implementation, not an invented SQL API.
Official Desktop JSON legacy auth/token endpoints are accepted as strict input
compatibility values while actual requests use fixed modern endpoints; synthetic
positive/negative fixtures are mandatory. No real client file was inspected.

M1-02 and this owner aligned restore representation: preserve verified bundle
state_instance_id, rotate namespace/owner, retain independent effect uncertainty
and require credential/binding/receipt consistency. Both proposals still require
independent exact-revision review. Added crash/CAS/replay/restore counterexamples
are planned acceptance, not executed tests. Only these two owned documents were
edited; no source, private credential, OAuth, commit, push or PR action occurred.

### Proposed early pure-value sequencing amendment r1

Date: 2026-10-02. Design-only dispatch from root; no source authorization yet.
Preserve the original approved plan's first 429 lines, SHA256
`a9e859b285c12715beb448a7cf85ecf4f3d9bfb3b6912cfe172ffda95732afce`,
and credential ADR's first 482 lines, SHA256
`bc1c6b993f27d2575d5759282fbbeb7fd67f125639e578ee31a63ee94ffba999`.
Their historical bases/review states stay unchanged. This appendix and the ADR's
matching early-pure appendix require a new independent exact-hash review.

Actual owned base is 1b7cd58; verified origin/main is
`f209fbe616dc65c70bbcdc4a104cf82b0d5dad27`, with actual integrated M1-01/P1-02
and separately reviewed M1-05 pure models/logging. No refs were changed while
drafting. Before a source dispatch, carry to the then-accepted main, record the
exact integrated input and revalidate compatibility. M1-02/M1-03 code remains
pending for credential storage/owner/receipt integration, not invented inputs.

This is a narrow exception to this plan's former all-source dependency ordering
and ADR's “before any source implementation” sentence, only for pure values and
in-memory codecs. It does not waive those gates for any actual credential use.
The ADR append-only finite allocation is the executable API contract: sixteen
named exports across three modules, plus an empty side-effect-free initializer.
It deliberately defers manager AccessSnapshot/VerifiedProfile/change records.

| Owned implementation file (future dispatch only) | Scope |
| --- | --- |
| `src/facet/gmail/__init__.py` | Empty __all__, no eager imports; root assigns single owner for this new shared seam |
| `src/facet/gmail/credential_models.py` | Closed private scalar/enums/three records, scope mapping and fixed errors; consume core and actual config validator |
| `src/facet/gmail/credential_codec.py` | Only strict bounded private envelope bytes↔model conversion |
| `src/facet/gmail/client_config.py` | Only Desktop client bytes→two-field value; no request/library object |
| `tests/unit/test_credential_models.py`, `test_credential_codec.py`, `test_oauth_client_config.py` | Exact inventory, grammar, scope/lineage syntax, roundtrip/negative controls |
| `tests/integration/test_credential_pure_privacy.py` | Synthetic subprocess output/log/lifecycle/import/installed-wheel and no-I/O controls |
| This plan and its credential ADR | Preserve approved prefixes; evidence appendix only after source dispatch |

No edits to DB/contracts/config/status/shared CLI/root docs/dependencies/CI.
No production file read/write, path/provider capability, token/profile exchange,
loopback listener, terminal/browser, credential manager, locks, receipts, binding
publication, usable snapshots or backup participant. A test may create its own
synthetic capture/wheel artifacts, never credential files or private state.
No payload comes from real accounts, client JSON, environment or spike files.

Required early acceptance, all planned rather than executed:

| ID | Paired detecting evidence |
| --- | --- |
| OP-01 | Fixed literal export/field inventories; exact required/nullability/type constructors; import no DB/OAuth/network/files/config discovery and no global logging mutation |
| OP-02 | All four role-compatible scope policies and valid authorization/refresh parent relationships; wrong role, excess/unknown/duplicate scope, bool/revision overflow, mismatched parent reject; success is not a grant attestation |
| OP-03 | Canonical envelope roundtrip preserves synthetic token/account and UTC microseconds only in returned memory; timestamp spelling normalization is not an artifact-digest equality claim |
| OP-04 | Depth/size boundaries and escaped-string depth positive controls; duplicate/extra/missing keys at every nested level, nonfinite/float/oversized integer, UTF-8/BOM/trailing JSON/unsupported version reject without raw errors |
| OP-05 | Official-shaped legacy and modern Desktop fixtures accepted; bad endpoint/host/port/userinfo/web root/extra keys/nonloopback/query/fragment reject; output cannot select outbound endpoint or callback |
| OP-06 | Hostile type/property/str/repr/eq/iterator/tzinfo plus uninitialized/corrupted exact models refuse before hooks; fixed errors retain no private original context/cause/args; valid expired envelope still structurally inspectable |
| OP-07 | Real subprocess stdout/stderr/files/log/shutdown sentinels absent on success and controlled refusal, both plain imports and actual M1-05 sealed bootstrap; explicit encode-buffer positive control and detecting privacy-oracle negative control |
| OP-08 | All four real public DTO serializers reject credential/client objects; no new private CLI/token output; installed wheel finite imports and exports preserve separate spike behavior; full baseline regression passes |

Use actual P1-02 guards; child processes install their own network prohibition.
Assert no credential discovery/file access via focused audit/spy controls without
mistaking normal interpreter/module loading for production credential I/O. No
test calls Google, makes a listener or obtains a runtime capability. Synthetic
caller-constructed grant/profile text is explicitly untrusted, not an oracle.

These tests cover only local syntax portions of OA-01/02/03/09/16/17/19.
OA-02 exchange provenance, OA-03/04 actual profiles/readiness, OA-05..08 flow/TTY/
receipt, OA-09 real secure files, OA-10..14 publication/crash/concurrency,
OA-15 actual failures/offline status, OA-16/17 real OAuth consumer output,
OA-18 backup participation and OA-20 CLI/container runbook all remain pending.
Do not mark a partly covered OA case passed by this slice or skip later E2Es.
Original r2 lost-candidate and restore regressions remain required unchanged.

After independent plan+API approval, root may dispatch this slice only, followed
by non-author exact candidate review, full locked baseline/Ruff/CLI helps/safety,
installed-wheel verification and actual CI before independent integration.
M1-04/its Issue/G1 remain open. Additional source scope, a new normalizer/public
capability or an unresolved private/public boundary requires a written amendment
and independent review first. SQL source QA remains higher priority for this owner.

### Early pure implementation handoff (2026-10-02)

Root dispatched source after a non-author independent review approved the exact
504-line plan SHA256
`044b4a0f7bdbab01ea0b33eac98e456b51a5b66a583e3b5fbfc62ab99f5f5ea3`
and 640-line ADR SHA256
`67e446fcd5319cb3fde596e15554b205ce5cd967717334f9f602c60b66081ac0`.
Those prefixes are preserved. The existing owned tree normally fast-forwarded
from 1b7 to actual accepted main `f209fbe616dc65c70bbcdc4a104cf82b0d5dad27`,
then switched to `feat/m1-04-credential-values`; no history rewrite or extra tree.
Root assigned the previously absent gmail initializer to this owner. Actual
initial main baseline: 488 tests passed on CPython 3.12.13 / SQLite 3.53.1.

Implemented only the four allocated source files and four allocated test files:
16 exact finite exports; private immutable structural values; bounded strict JSON
envelope codec; two-field Desktop client parser. No function reads a file, uses
network, validates a real grant/profile, changes binding, publishes credentials,
or creates a runtime capability. Production paths/Google clients are not imported.

Local evidence before independent source review:

| Case | Actual evidence and boundary |
| --- | --- |
| OP-01/02 | Fixed export/record field sets, required exact constructors, all four scope-policy pairs and authorization/refresh parent syntax; no deferred capability exports |
| OP-03/04 | Private byte roundtrip and explicit token-memory positive control; canonical UTC, duplicate/missing/extra keys, invalid numbers/UTF-8/BOM/version, exact byte cap and depth lexer positive/negative boundary |
| OP-05/06 | Legacy/modern official-shaped synthetic client inputs and numeric loopback positive controls; hostile endpoint/URI/model/subclass/descriptor/timezone objects and corrupted exact values reject with fixed errors/no original context |
| OP-07/08 | 13 real subprocess cases with child network guard: plain/sealed success/refusal, actual buffered logger shutdown, detecting output negative control, no function file I/O, empty output directory, unchanged import logging policy and all four actual public DTO families rejecting private objects |
| Full regression | 608 passed (488 baseline +120 new); Ruff check and format 91 files passed; both CLI helps and repository safety passed |
| Distribution | Built wheel; installed non-editably into a fresh task-only venv with the existing locked PyYAML version offline; Python -I imported from site-packages, verified all 16 exports and a private in-memory roundtrip without DB/CLI/spike/Google imports |

Wheel/bootstrap used no new dependency or lock change. The cross-filesystem cache
hardlink warning fell back to copying successfully; it was not a failed gate.
These are local engineering results, not independent source approval or CI/
integration evidence. Candidate SHA and exact external receipts belong to the
Issue/PR handoff, avoiding self-referential report commits. All original full OA
consumer, actual secure file/manager/writer/CLI, D3, M6 and G1 gates remain pending.
Neither this partial unit nor its tests close M1-04.
