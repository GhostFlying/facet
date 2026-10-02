# ADR: private OAuth credential manager v1

Date: 2026-10-02. Package M1-04. Proposed version `m1-credential-v1`, revision r2.
Status: design authoring; NOT reviewed/frozen or permission to implement.
Original base: `c18bfbee09b985ee7b9bb5c230ee2a70427c7edc`.
Actual owned base: `1b7cd58b4846aab86edcbb781a999abb968d047c`.
Author: delegated phase1_architecture_plan; independent reviewer required.

Implements the independently approved [M1-04 plan](../m1-04-oauth-binding.md),
original SHA256 `fbc37240dd2fbeb920f835d15fb2456aceec9d15f73fb19072f6bbdfd07ac803`.
Preserves [core v1](core-state-contracts.md), [writer v1](writer-command-protocol.md)
and [CLI/privacy contract](../../cli-spec.md). No live OAuth/Gmail, account
configuration, revocation, scope expansion or credential-file inspection occurred.
This is OAuth account authorization, NOT M1-06 sender-authentication trust.

## Ownership and review gates

M1-04 owns the records/algorithms below in its planned gmail credential modules.
Import canonical core primitives/enums; no new shared enum copy or broad provider
protocol. New credential-only enums below are private to this module. These
records do not imply existing DB tables, SQL repository signatures, CLI wire
variants, owner capabilities or public DTOs. M1-02/M1-03 must accept their required
semantic seams in independently reviewed extensions before source implementation.
M1-05 alone integrates global sealed logging/public status. M2-01 integrates
worker HTTP adapters later; M6 owns complete backup/restore and container proof.

Actual M1-01 merged executable input is b1e4ae08f7e361518eaa4f7fb1ae9f7f0b278f28;
P1-02 CT actually merged at 1b7cd58b4846aab86edcbb781a999abb968d047c;
root verified post-merge main CI 36982879970. Root authorized the normal base
carry to that SHA preserving these two drafts; no dependent source is written.
M1-02 schema is only a proposal and M1-03 wire is not implemented.
Exact versions/SHAs, accepted storage/command extension mappings and root dispatch
are hard implementation gates; no worker fills gaps with a dict or private SQL.

## Closed credential data model

All listed fields are required, including nullable ones. Records are immutable;
repr/str never include secret/identity values. No arbitrary provider JSON/text.
Unknown stored fields/tags/versions, duplicate keys, non-finite numbers, coercion
and trailing objects are invalid. UTF-8 JSON envelope maximum 131072 bytes,
depth 8; field strings have bounds below. JSON numbers must be actual integers,
not bool. Version 1 only. Times use core Timestamp semantics serialized as UTC
RFC3339 with `Z` and at most six fractional digits; expiry cannot be guessed as
infinite when absent. LocalId/Revision/Role reuse p1-core-v1; increments check
overflow before effect. Secrets remain strings only in the private memory/file
boundary, never DB/receipt/snapshot-for-public-output.

Credential-local scalar definitions:

| Type | Validation / serialization |
| --- | --- |
| SecretText | Nonempty UTF-8 string, maximum 16384 bytes, no C0/control/surrogate characters; opaque, never normalized or logged |
| ClientIdText | Nonempty ASCII string, maximum 1024 bytes, no whitespace/control; private metadata, not an executable URL |
| AccountAddress | Exact reviewed config/binding normalization; private address; no dot/plus/alias inference; M1-01 normalization is the one implementation |
| ScopeName | Closed strings `gmail_readonly`, `gmail_insert`, `gmail_modify`, `gmail_labels`; maps to exact `https://www.googleapis.com/auth/gmail.*` URI in outbound exchange only |
| ScopeSet | Nonempty immutable set of ScopeName, serialized sorted unique array; max four; unknown/duplicate stored values rejected |
| ScopePolicy | `source_readonly`, `source_convenience`, `target_default`, `target_labels`; each role-compatible only |
| GrantEvidenceKind | `authorization_explicit`, `authorization_omitted_equal`, `refresh_explicit`, `refresh_omitted_inherited` |
| CredentialChangeKind | `authorize`, `reauthorize`, `refresh` |
| CredentialChangePhase | `requesting`, `validated`, `committed`, `abandoned`, `attention` |

Scope-policy mapping is exact: source_readonly={readonly}; source_convenience=
{modify}; target_default={insert,readonly}; target_labels={insert,readonly,labels}.
The word fragments in this sentence stand for ScopeName values above. Default
setup only enables source_readonly/target_default. Convenience/labels are inert
until the separately reviewed explicit mode/scope choice is durably authorized;
reauth cannot select a policy different from the approved binding's policy.
No superset is silently accepted: actual grants must equal the selected policy.
Policy change needs its separately scoped command/consent workflow, not this
reauth path. No revoke or cloud-console change is automated to shrink grants.

Records owned by the credential module:

| Record | Exact fields |
| --- | --- |
| GrantEvidence | `kind: GrantEvidenceKind`, `granted: ScopeSet`, `requested: ScopeSet`, `observed_at: Timestamp`, `parent_credential_revision: Revision|null` |
| ProviderSecret | `client_id: ClientIdText`, `client_secret: SecretText`, `access_token: SecretText`, `refresh_token: SecretText`, `expires_at: Timestamp` |
| CredentialEnvelope | `version: int=1 literal`, `projection_id: ProjectionId`, `state_instance_id: LocalId`, `role: Role`, `binding_revision: Revision`, `credential_revision: Revision`, `change_id: LocalId`, `account: AccountAddress`, `scope_policy: ScopePolicy`, `scope_policy_revision: Revision`, `grant: GrantEvidence`, `profile_verified_at: Timestamp`, `secret: ProviderSecret` |
| AccessSnapshot | `role: Role`, `credential_revision: Revision`, `binding_revision: Revision`, `scope_policy_revision: Revision`, `access_token: SecretText`, `expires_at: Timestamp` |
| VerifiedProfile | `role: Role`, `account: AccountAddress`, `verified_at: Timestamp` |
| CredentialChange | `change_id: LocalId`, `role: Role`, `kind: CredentialChangeKind`, `phase: CredentialChangePhase`, `old_revision: Revision`, `new_revision: Revision`, `binding_revision: Revision`, `scope_policy_revision: Revision`, `operation_id: LocalId|null`, `supersedes_change_id: LocalId|null`, `started_at: Timestamp`, `updated_at: Timestamp`, `candidate: CredentialCandidateMetadata|null`, `error: ErrorCode|null` |
| CredentialCandidateMetadata | `envelope_digest: Sha256Hex`, `scope_policy: ScopePolicy`, `grant: GrantEvidence`, `profile_verified_at: Timestamp`, `expires_at: Timestamp` |

These are module value records, not a new Binding, Operation or storage schema.
CredentialChange and candidate metadata are the requested metadata-only storage
extension. A digest covers the exact private envelope bytes for crash consistency,
not proof of account authenticity; it is private artifact metadata and never
public telemetry. No secret bytes, provider response or client secret are in it.

Envelope/change revisions are positive; old_revision=0 means no accepted token,
new_revision=old_revision+1. Binding/policy revisions must equal the accepted
binding metadata. One unresolved change per role; a role has no usable snapshot
while its change is requesting/validated/attention. Authorize requires old=0;
reauthorize requires old>0; refresh requires old>0 and existing attested lineage.
Authorize/reauthorize require operation_id; refresh has None. requesting has no
candidate/error; validated/committed require candidate and no error; abandoned
requires a fixed error and retains candidate metadata if previously validated;
attention may retain candidate and requires error. committed/abandoned are
terminal change phases. supersedes_change_id is null for ordinary changes and
all refreshes; only the explicit replacement transaction below may set it, to
the exact same-role abandoned predecessor. It is immutable, never self-referential,
and cannot authorize replacing a committed change. Cross-record predicates are validated again by
the owning repository, not trusted solely because Python records constructed.

GrantEvidence authorization kinds require parent=None and requested=the approved
policy; refresh kinds require parent=old_revision and a valid previous grant.
All grants equal the selected policy. Refresh parent must be exactly the previous
accepted revision; no circular lineage. Envelope account and role equal private
binding, account differs from other role. profile_verified_at on refresh carries
the last accepted same-account live verification time, not a new claim that
refresh itself queried profile. AccessSnapshot contains neither refresh token,
client secret, file path nor mutable library Credentials object.

## Where actual-scope evidence comes from

The module observes the bounded successful token exchange response directly in
memory through the approved library's HTTP response adapter before extracting
allowlisted fields. Trusted here means TLS-verified response from the fixed
Google token endpoint in this exact correlated exchange, not an arbitrary dict
loaded from disk and not requested scopes passed to a Credentials constructor.
Tests inject a fake exchange explicitly; fake success is not real grant evidence.

| Exchange | Scope response | Evidence and rule |
| --- | --- | --- |
| New authorization-code exchange | Present | Parse actual scope strings; require exact selected policy; authorization_explicit, parent None |
| New authorization-code exchange | Omitted | RFC6749 §5.1 omission means equal to the scope requested in this successful, state/PKCE-correlated authorization exchange; authorization_omitted_equal, parent None. No prior credential is needed |
| Refresh | Present | Parse response grant, require exact approved policy and no scope outside prior attested grant; refresh_explicit, parent old revision |
| Refresh | Omitted | Refresh sends no scope parameter; RFC6749 §6 defaults to original grant. Inherit only the validated previous envelope's attested grant; refresh_omitted_inherited, parent old revision |
| Imported/unrecognized token file or response absent outside exchange | Any local `.scopes`, `has_scopes`, config desired set | Not evidence; refuse credential import or require explicit new auth |

OAuthlib normalization must not obscure whether the server actually supplied
scope. Observe presence before library fallback, reject malformed/duplicate
scope strings and bounded response parse failures, and handle the library's
scope-change warning without logging its raw exception. Unknown grant URIs fail
with scope_required; do not emit them. Credentials.has_scopes is at most an
additional consistency check after this evidence, never the source of truth.

New auth/reauth requires a returned refresh token; missing means no replacement
and auth-required, not silently reuse a token from another flow/account. During
refresh only, absent new refresh token retains the prior one; a supplied new
refresh token replaces it. The server may rotate/revoke the old token before
local persistence; loss in that window can require user reauth. We do not claim
atomic provider/file/DB updates or recover a lost new refresh token magically.

## Desktop client and local callback boundary

One explicit owner-only Desktop client file at the configured private location
is read only during dispatched auth, not discovered via HOME/ADC/spike state.
Reject `web` client type and conflicting/unknown credential configurations.
Validate client ID/secret as above. Outbound authorization endpoint is fixed
`https://accounts.google.com/o/oauth2/v2/auth`; token endpoint is fixed
`https://oauth2.googleapis.com/token`. No endpoint, token audience, quota project,
universe domain, refresh handler or proxy command is taken from token JSON.
TLS verification stays on. No process-global insecure-OAuth environment setting.
Desktop JSON root is exactly `installed`, an object with required `client_id`,
`client_secret`, `auth_uri`, `token_uri`, `redirect_uris`; optional `project_id`
and `auth_provider_x509_cert_url`. All other fields fail validation. Required
auth_uri accepts exactly `https://accounts.google.com/o/oauth2/auth` or
`https://accounts.google.com/o/oauth2/v2/auth`; token_uri accepts exactly
`https://accounts.google.com/o/oauth2/token` or
`https://oauth2.googleapis.com/token`. These are compatibility values in official
Google client-file formats, not outbound endpoint selection. Equality is exact:
no alternative domain, port, userinfo, query, fragment, percent-encoded spelling
or trailing slash. No operator edit of the downloaded secret file is required.
After validating the input, construct a fresh bounded in-memory library config
from the validated client ID/secret and the fixed modern outbound endpoints
above; do not hand the original file/object to a helper that selects its URLs.
The legacy token URI is accepted as file metadata only and is never contacted.
`redirect_uris` is an array of
1..16 distinct strings of at most 2048 bytes; accepted entries are Desktop
loopback registrations (`http://localhost` or numeric loopback HTTP URI without
query/fragment/userinfo); entries do not select the actual callback destination.
Optional project_id is at most 256 ASCII bytes, x509 URL if present is exactly
`https://www.googleapis.com/oauth2/v1/certs`. These two metadata fields are ignored,
never copied to the envelope. File has the same 131072-byte/depth/duplicate-key
limits as the envelope and exact locked-library integration tests before use.

Use InstalledAppFlow authorization_url/fetch_token primitives, not its unmodified
run_local_server helper. Supply explicit random 256-bit state and 64-character
cryptographically generated PKCE verifier; S256 challenge. Use access_type=offline,
prompt=consent and the exact role-policy scopes; no incremental grant merging.
State/verifier/code/complete callback URL remain memory-only. Library fetch_token
receives the original correlated state, exact redirect and verifier; token/profile
calls have 30-second deadlines and no automatic authorization-code retry.

Facet's thin one-shot listener binds 127.0.0.1 and explicit port 1024..65535 before
showing the URL; redirect is exactly `http://127.0.0.1:<port>/oauth/callback`.
No fallback to all interfaces/localhost/another port. Callback has total deadline
300 seconds and per-connection read deadline 5 seconds, max request line/query
8192 bytes and max headers 16384 bytes. Only GET on the exact path and Host
`127.0.0.1:<port>`; no request body. Reject duplicate state/code/error fields,
require exact state and exactly one of code/error. Compare state in constant
time; invalid callback does not consume the valid flow, but 16 rejected callbacks
terminate it with fixed input error. A valid response consumes it once. Static
no-store response says only that authorization response was received; it is not
proof that profile/file/DB acceptance succeeded. No reflected URL/error/account.

No callback request logging or generic HTTP access logger. The adapter never
passes code/URL in a child-process argv or exception message. Browser opening,
when explicitly selected, uses the platform browser facility only after the
same terminal/role confirmation; errors are sealed. URL is written exclusively
to opened controlling terminal, never stdout/stderr/log/receipt. Absence of a
controlling TTY refuses before network even with --yes. JSON stdout remains one
CLI envelope. SSH port forwarding is operator setup, not executed by Facet.
All exits close listener and discard flow references; no OOB/code-paste fallback.

## Profile and startup verification

Only `users.getProfile(userId="me", fields="emailAddress")` is called here.
Parse bounded expected response, normalize with the canonical config address
validator, compare configured+stored role binding and the other account. Missing,
malformed, same-account or swapped identity rejects before replacing credentials.
Never derive account identity from login_hint, client-provided account text or
scope success. No extra identity scopes or mailbox content/history probe.

On fresh daemon start under owner ownership, validate local envelopes and pending
changes first; do not issue snapshots until required refresh/profile checks finish.
Both roles must verify in this owner run before new Gmail writes. Same-role
refresh can use the previously attested envelope to obtain access for its profile
check, without marking the projection ready early. Late profile responses carry
owner run/binding/credential revisions; stale results cannot update readiness.
Wrong identity preserves binding and blocks the role; network/auth dependency
failure preserves jobs and offline status. Successful reauth/profile never clears
daemon pause, stopped generations, unknown inserts or restore-effect revalidation.

## One single-flight change and durable publication

Owner EX is mandatory before any token read capable of refresh/replacement.
Normal daemon holds it for lifetime; stopped auth holds it through browser waits.
Role mutexes protect manager state. Source precedes target for two-role operations;
normal one-role refresh does not take view EX. Never wait for writer acknowledgment
with role mutex held, and never wait for network with a SQLite transaction open.
One single-flight slot per role stays reserved while the mutex is released.
Other same-role callers wait on its bounded completion event outside the mutex;
different roles can progress independently. Caller timeout does not cancel an
already accepted credential commit or start a second refresh.

Algorithm (all writer steps are requested through the actual reviewed owner,
not direct SQL from a refresh worker):

1. Under role mutex validate local state, reserve change_id/new_revision and set
   publication closed. Release mutex. Writer durably creates requesting metadata
   by old-revision CAS before network. Failure means no request/token replacement.
2. Reacquire role mutex for exchange/flow's secret work; no DB transaction. Obtain
   candidate, validate scope and, for auth/reauth, profile before replacing any
   accepted credential. Build immutable envelope; encode exact bounded bytes
   and compute private digest. Retain candidate only in bounded manager memory.
3. Release mutex; writer CAS requesting→validated with candidate metadata.
   No secrets traverse this call. On failure do not write token or serve candidate.
4. Reacquire mutex, verify same reserved change/revision/owner and write envelope
   to `credentials/.<role>-<change_id>.pending` with exclusive/no-follow create,
   mode0600. File fsync, atomic replace fixed `<role>-token.json`, directory fsync.
   Role snapshot remains closed. Existing unsafe file/symlink aborts, no chmod.
5. Release mutex; writer CAS validated→committed and binding credential_revision,
   safe grant/expiry metadata, plus A-workflow completed receipt in one short
   transaction. This semantic transaction must be accepted by M1-02/M1-03.
6. After durable acknowledgment, reacquire role mutex, require matching owner,
   change/revision and envelope digest, publish immutable AccessSnapshot and
   clear single-flight slot. No stale callback may reopen an older revision.
   Notify waiters after releasing mutex. New call checks expiry/current readiness.

On invalid grant/profile/scope before validated, writer records abandoned or
attention with controlled error and leaves accepted file/revision unchanged.
Invalid_grant closes role access and requires reauth. Transient dependency failure
may abandon this refresh attempt and retain old accepted revision, but expired
snapshots remain unusable. An interrupted authorization code is not retried or
restored from disk; an explicitly new interactive workflow may be needed.

The finalization transaction does not automatically mark startup/live binding
verified; that is the separate both-profile gate. During refresh, outstanding
snapshots already supplied to bounded in-flight operations cannot be recalled.
New requests cannot obtain one while publication is closed. Reauth/restore require
stopped owner, so no old daemon worker survives token replacement legitimately.

## Crash and error table

Restart reconciliation runs before manager publication under the new owner.
Recognize fixed role file and at most the exact pending path named by durable
change_id. Never scan/adopt arbitrary token files or import unknown legacy JSON.
Digest/role/lineage/binding/policy/revision must match metadata; mismatch is
attention and zero new snapshots. Old bytes are not blindly restored as usable.

| Durable state / interruption | Restart result and forbidden shortcut |
| --- | --- |
| No requesting record | No change accepted; old envelope consistency still checked; no automatic consent |
| requesting before/during remote call, no candidate metadata | Record interrupted/abandoned auth-required; retain old file but do not claim remote grant unchanged; refresh may have rotated remotely, so fresh checked refresh or explicit reauth is needed |
| Candidate only in memory, validated commit failed | Candidate is lost; old accepted state remains; never pretend new token persisted or replay authorization code |
| validated, old final file (or absent on first auth), no complete pending file | Cannot reconstruct secret; mark attention/auth-required, preserve metadata and old file; old_revision=0 permits explicit new authorize, old_revision>0 permits explicit new reauthorize, only through the replacement transaction below |
| validated, exact complete pending file fsynced | Validate exact digest/metadata then finish replace+directory sync and finalization; incomplete/mismatching temp remains attention, not accepted |
| After replace before directory fsync | On restart inspect actual final/pending files; exact candidate can be fsynced/finalized, exact old only follows previous row; absence/mismatch is attention, never guessed success |
| Final candidate durable, final DB CAS failed/not acknowledged | Exact validated metadata plus final envelope permits idempotent finalization; until then no publication; DB failure leaves explicit blocked persistence state |
| committed before cache/first CLI response | Verify final envelope then rebuild cache subject to startup profiles; A lookup returns original completed receipt, never repeat consent/replacement |
| File/new metadata mismatch or unsupported envelope/lineage | attention/consistency_failure; offline maintenance possible, no empty DB, rebind or file adoption |
| Restore/incomplete maintenance marker | M6 bundle protocol first; no credential recovery/publication across incomplete bundle; fresh namespace does not freshen old A request keys |

If an operation cannot complete because candidate secrets were lost, its A receipt
stays needs_attention with its original key. Same-key replay returns that state,
not a new OAuth run. Replacement uses a new stable request key and explicit
confirmation of the selected old change, role and unchanged binding/policy.
This is a semantic requirement on M1-03's pending A registry, not a new CLI flag
or invented wire/API. The exact private supersedes_change_id is included in its
semantic digest; changing the selection on the same key is request_conflict.

Under stopped owner ownership and the reserved role slot, first reconcile the
selected change's exact final/pending paths. A complete matching candidate wins:
finish its durable publication and original receipt before considering a new
flow. An fsync/DB failure remains blocked; it is not evidence of candidate loss.
Foreign/mismatching final files, uncertain file inspection or changed lineage
remain consistency_failure, never permission to overwrite. Replacement is
eligible only after positive classification of no publishable candidate, with
an exact old accepted final file when old_revision>0 or absent final file when
old_revision=0. A known incomplete old pending file is not published or adopted;
it remains private under its recorded old change identity, not reused by the new
change. No arbitrary directory scan, blind token rollback or automatic revoke.

Release the role mutex before one short writer transaction. Its compare-and-swap
matches the entire previously read predecessor CredentialChange (including phase,
candidate/digest and updated_at), current accepted credential revision, binding
revision, policy revision and current owner run. Any change aborts all effects
and requires reinspection; elapsed time is not a guard. Only requesting/validated/
attention predecessors may be abandoned. In that same transaction:

1. Mark the predecessor abandoned with the role's fixed auth-required error,
   retaining its metadata and operation reference. If it has an A operation,
   make that original receipt rejected with the same controlled code; this means
   its local credential publication did not complete, not that Google issued
   no token. Refresh predecessors have no receipt to fabricate.
2. Accept the new A operation and insert its requesting change, linked by
   supersedes_change_id. Accepted revision 0 requires kind=authorize; positive
   accepted revision requires kind=reauthorize. Both require a new operation_id
   and change_id, new_revision=current accepted revision+1, same role/binding/
   policy. The lost unaccepted candidate does not increment the accepted revision.
   New change identity/digest prevents an old candidate at that same revision
   from being adopted. The one-unresolved-per-role constraint holds at commit.

Only after durable acknowledgment may the new exchange begin. Crash before the
transaction leaves the old attention state; crash after it leaves the new key's
requesting workflow for ordinary interrupted-flow recovery. Lost acknowledgment
uses new-key lookup, never a second exchange or another automatic key. Replay of
the old key after replacement returns its rejected receipt; it cannot restart
OAuth. If the predecessor already became committed, recover that receipt and
reject this replacement selection rather than silently starting a normal reauth.
No jobs, unknown insert attempts, pause/stopped state or restore fences change.

## CLI, public output and third-party diagnostics

A workflow semantic fields are role, change kind and expected binding/policy
revisions, plus the standard projection/request identity and confirmation.
Scope policy is obtained from approved binding, not arbitrary URI strings in CLI.
Port/browser choice is transport-only and cannot alter semantic grant. M1-03
owns exact wire/digest/operation integration and must register this through its
reviewed extension; no claim that an existing CommandEnvelope already contains A.
Stable client key/journal precedes acceptance; first-response loss lookup and
restored-key lineage use writer v1 unchanged. Running daemon refuses interactive
auth; never transfer secrets over Unix command IPC or Web.

Offline auth-status uses read-view metadata only, never loads a refresh-capable
Credentials object. Safe local role status contains role, configured mode,
scope-ready boolean/unknown, last profile verification time, expiry time/unknown,
fixed credential health category and freshness. Exact output schema belongs to
M1-05; no addresses, digest/revisions, IDs, paths or scopes in public output.
Necessary private account metadata requires explicit private profile. No mode
permits token/code/client secret/URL/provider error or mail contents.

Install sealed third-party logging policy before importing/using OAuth clients:
google_auth_oauthlib, oauthlib, requests_oauthlib, google.auth, google.oauth2,
googleapiclient, urllib3 and httplib2 records cannot propagate to production sinks;
drop their original records, do not format then redact. Application logger emits
only manually selected core ErrorCode/role/counters, never exception repr/args,
exc_info, HTTP wire debugging or request headers. Disable HTTPConnection debug
printing and library debug handlers at process initialization; detect unsupported
debug configuration and refuse auth/network initialization. M1-03/M1-05 own the
actual global logger bootstrap; its acceptance is an implementation dependency,
not temporary monkeypatching around concurrent calls. Test with DEBUG-enabled
third-party loggers, malicious error bodies and token URLs before enabling I/O.

Google errors are parsed only within bounded memory. Map invalid_grant/401 to
role auth-required; timeout/connect failures to network_unavailable; partial or
unapproved scope to scope_required; wrong profile to binding_mismatch; filesystem
failure to persistence_failure; malformed/internal inconsistent state to
consistency_failure. OAuth denied or missing terminal maps confirmation_required;
port/owner conflict owner_busy; callback invalid_input; listener timeout wait_timeout.
No free-form reason string survives. Retry/recovery policy for Gmail writes stays
M2-01/M2-04; credential refresh failure never directly repeats an insert.

## Backup and restore participation

M6 takes owner EX→view EX→source role mutex→target role mutex. A different process
cannot race refresh/reauth because it cannot get owner. Role locks still enforce
in-process order. Backup inventory is exactly the approved Desktop client file
and fixed accepted per-role envelopes plus required metadata manifest; unresolved
credential change is a failed consistency check, not a silently complete backup.
M6 may preserve an incomplete diagnostic backup separately but cannot label it
restorable complete. No raw email or request/response dump belongs in the bundle.

Restore preserves state_instance_id lineage of the restored bundle and rotates
request namespace/owner as writer v1 requires. Envelope identity/revisions must
match restored binding metadata; namespace is intentionally not an envelope
field, so namespace rotation does not rewrite secrets. Loaded snapshots stay
closed until new live profiles verify; restore-effect fence stays independent.
Instance identity is not a restore epoch or proof of absence of remote effects.
For example, an insert or accepted A request after the backup can be missing from
the restored DB even though its instance matches every credential envelope.
Old-key receipt absence therefore still fails the namespace guard; rediscovered
unmapped mail remains fenced, including after successful reauth. Preserving the
instance does not preserve the old owner run's live readiness. The complete bundle
must restore matching credential/binding/change/receipt metadata; partial/mixed
revisions refuse publication. No token rewrite or artificial credential revision
increment is needed merely to rotate the request namespace. This representation
is coordinated with the M1-02 r2 proposal but neither proposal self-freezes;
both independent reviews and the actual maintenance extension remain gates.
M6 alone owns filesystem bundle journal/switch/rollback; M1-04 does not bypass it
or require Gmail availability for offline inspect/backup/restore validation.

## Required extension handshake and acceptance

Before any source implementation, root records independent approval of this
ADR plus M1-02/M1-03/M1-05 alignment outcomes:

- M1-02: one unresolved CredentialChange per role, revision CAS, bounded private
  metadata storage and candidate fields, exact commit/failure/read-view queries;
  no token/client response SQL columns. Its schema/repository extension owns names.
- M1-03: lifecycle owner capability, role mutex manager registration, A durable
  request/lookup semantics, final credential+receipt transaction and sealed
  bootstrap; replacement predecessor CAS, old receipt rejection and new receipt/
  change admission in one transaction. No worker direct SQLite connection/second DB writer.
- M1-05: exact offline/local/public auth DTO, controlled logging bootstrap and
  fixed-code extension only if existing codes cannot express a reviewed result.
- M2-01 later: manager-mediated immutable snapshots and no worker auto-refresh,
  separate per-worker HTTP transport; cannot become a prerequisite for M1-04's
  bounded synthetic exchange tests.
- M6 later: same state UID/volume locks, complete-envelope backup/restore and
  container loopback/SSH route. Host/network actions require separate authority.

OA-01..20 in the approved plan remain mandatory. Add each crash-table row to
OA-10/11 with actual child-process termination as well as injected exceptions;
OA-02 tests fresh omitted scope without previous credential separately from
refresh omission with/without attested lineage; OA-12/14 exercise mutex release,
single-flight reservation, late CAS and closed publication; OA-16/17 cover every
secret path/logger including negative controls. These are required future tests,
not results. No source, SQL, tests, credential files or live APIs were changed.

R2 review regression requirements (future tests, not executed here):

- OA-08/10/11: first authorize old=0 loses validated candidate; old-key replay
  never exchanges again, while explicit new authorize can atomically replace it.
  Repeat with old>0/new reauthorize, and refresh predecessor with no A receipt.
  Wrong replacement kind, changed binding/policy/predecessor or two concurrent
  new keys must not pass CAS. Assert one new accepted change and call counts.
- Kill before/after replacement transaction and lose its acknowledgment; each
  key remains discoverable with no partial old-abandon/new-admit pair. Recover
  a matching fsynced pending/final candidate first; forbid replacement on inspect/
  fsync/DB failure, mismatching final or a now-committed predecessor. A stale old
  candidate sharing the new revision cannot pass change_id/digest checks.
- OA-09: synthetic official installed client fixtures with legacy auth+token
  URIs and modern URIs both validate unchanged; assert actual library requests
  use only fixed modern endpoints and selected loopback redirect. Reject web,
  non-Google/lookalike hosts, userinfo, endpoint queries/fragments/ports, altered
  paths and non-loopback redirects before outbound work. No real client JSON.
- OA-18: restore matching bundle with retained instance and new namespace/owner;
  old missing request stays lineage_mismatch, known receipt stays historical,
  profiles cannot release unknown post-backup insert work. Mixed credential/DB
  revision or old-run readiness fails; namespace rotation alone never rewrites
  secret files. Real bundle E2E remains M6's evidence, not a model-test claim.

## References and limits

Read-only protocol/library sources were checked during the plan on 2026-10-02:
[Google Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[RFC6749 token response/refresh](https://www.rfc-editor.org/rfc/rfc6749),
[Google credentials](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.credentials.html),
[Flow API](https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes).
R2 additionally checked Google's
[installed client-file example](https://developers.google.com/api-client-library/dotnet/guide/aaa_client_secrets)
for legacy auth/token URI compatibility; it is format evidence, not a reason to
take the outbound endpoint from the input file.
Implementation must recheck the exact locked library source: online reference
versions may lag. No OIDC scopes, DPoP/key-store framework, token broker or
automatic revocation is introduced. External Testing token expiration and
Workspace policy may still require user interaction. D3 permission is absent;
offline design and fake exchanges do not grant it or close live/G6 gates.

## Proposed early pure-value sequencing/API amendment r1

Date: 2026-10-02. Root dispatched design only; independent approval and a later
explicit source dispatch are required. The first 482 lines remain the accepted
r2 artifact, SHA256
`bc1c6b993f27d2575d5759282fbbeb7fd67f125639e578ee31a63ee94ffba999`.
This appendix is the sole bounded exception to the earlier “before any source
implementation” dependency wording. All manager/file/CLI/participant code still
requires the original storage/writer/output handshake. No API below accepts an
owner, DB session, path, file object, provider response or network callback.

The early unit depends on actual integrated core/config/P1-02 and M1-05, currently
available together at main `f209fbe616dc65c70bbcdc4a104cf82b0d5dad27`.
The design worktree remains at 1b7; source dispatch must carry to the actual
accepted main first and record its exact SHA without rewriting these prefixes.
No M1-02 moving source or proposed M1-03 interface is an input to this unit.

### Finite allocation and exports

The package `facet.gmail` is new at the accepted main. Its initializer has empty
`__all__`, no eager imports and no setup side effects. Root must assign this one
shared initializer to the early owner before implementation; later owners extend
it only through a reviewed handoff. Three modules own the following exact exports:

| Module | Exact public export names |
| --- | --- |
| `credential_models.py` | `SecretText`, `ClientIdText`, `AccountAddress`, `ScopeName`, `ScopeSet`, `ScopePolicy`, `GrantEvidenceKind`, `GrantEvidence`, `ProviderSecret`, `CredentialEnvelope`, `CredentialCodecError`, `policy_scopes` |
| `credential_codec.py` | `encode_envelope`, `decode_envelope` |
| `client_config.py` | `DesktopClientConfig`, `parse_desktop_client` |

The first ten model names use exactly the r2 fields/scopes above, not a second
core enum inventory. SecretText/ClientIdText/AccountAddress each have one required
`value:str`; ScopeSet has one required `value:frozenset[ScopeName]`, 1..4 members.
The three enums ScopeName/ScopePolicy/GrantEvidenceKind use their exact r2 values.
The three records GrantEvidence/ProviderSecret/CredentialEnvelope have exactly
the fields listed in r2, all required, including the nullable parent revision.
Records/scalars are immutable, slotted, fixed safe repr/str with no field values.
No auto-generated field formatter, generic asdict/to_dict or pickle API is added.
Secret values necessarily remain explicitly accessible in private memory; this
is not protection against malicious code introspecting the process.

AccountAddress first requires exact builtin str, at most 1024 UTF-8 bytes, then
uses the actual M1-01 `facet.config._mailbox` validator as a named internal
dependency. That validator preserves spelling: no new case/dot/plus/IDNA rule
is introduced. Do not copy its implementation or add a fake public normalizer.
This envelope resource bound does not change the config parser's own bounds.
An eventual shared-public normalizer needs its owner-reviewed extension.
SecretText rejects Unicode Cc/Cs characters; ClientIdText rejects non-ASCII,
whitespace and controls; their size limits remain those in r2.

Constructors and boundary functions reject wrong exact types before attribute,
iteration, equality or formatting access. They revalidate nested fields, including
uninitialized or deliberately corrupted exact records, rather than treating class
membership as proof. Core values are imported, not redefined; verify their scalar
payload bounds without calling unsupported hooks. Timestamp payload must be exact
datetime with a standard-library timezone instance and zero UTC offset before
formatting/comparison; custom tzinfo callbacks are unsupported at this boundary.
Accepted timestamps retain the core UTC instant and microseconds, no hidden clock.

Local envelope consistency requires version exact int 1 (not bool); positive
binding/credential/scope-policy revisions; matching role-policy pair; granted=
requested=policy_scopes; authorization parent=None, refresh parent positive and
equal to credential_revision-1. Profile/grant times and expiry must be valid UTC
timestamps, but expiry in the past is allowed for offline inspection: no “now”
or healthy/usable result exists here. GrantEvidence alone validates nonempty equal
scope sets and parent-kind shape; envelope supplies policy/revision relationships.
No fabricated cross-account binding check or real exchange is performed.

`CredentialCodecError(code:ErrorCode=INVALID_INPUT)` permits only INVALID_INPUT
or UNSUPPORTED_VERSION. Invalid error constructor inputs themselves yield fixed
INVALID_INPUT without invoking their hooks. Error args/repr/str contain only the
fixed code, never original bytes, parser exception, JSON offset/snippet or record.
Wrap parser/constructor failures outside the caught exception scope so the raised
controlled error retains no raw exception context/cause. Never log exceptions.

The following r2 records remain entirely deferred, not placeholder exports:
AccessSnapshot, VerifiedProfile, CredentialChange, CredentialCandidateMetadata,
CredentialChangeKind and CredentialChangePhase. Especially no usable snapshot
factory or “verified” profile constructor is introduced by this early slice.

### Exact pure signatures and wire grammar

| Signature | Result / finite rules |
| --- | --- |
| `policy_scopes(policy:ScopePolicy, role:Role) -> ScopeSet` | Exact r2 mapping, wrong role-policy refuses; returning a set is not scope-selection authorization |
| `encode_envelope(value:CredentialEnvelope) -> bytes` | Revalidate the complete finite tree, then canonical private UTF-8 JSON; no I/O or logging |
| `decode_envelope(raw:bytes) -> CredentialEnvelope` | Exact builtin bytes only, strict bounded JSON and finite schema; structural value only, not attestation |
| `parse_desktop_client(raw:bytes) -> DesktopClientConfig` | Same bounded parser, exact r2 installed input grammar; discard original JSON and ignored metadata |

Each function either returns the exact listed value or raises CredentialCodecError;
there are no generic result dictionaries, callback parameters or side effects.
DesktopClientConfig has exactly two required fields: `client_id:ClientIdText` and
`client_secret:SecretText`, immutable and safe repr/str. It contains no endpoint,
redirect choice, project/quota setting, refresh token or library credential object.
It is only validated client-file content, not an initialized OAuth flow.

Envelope JSON object keys are exactly its r2 field names. Each scalar wrapper is
its primitive string/integer, each enum its exact value, ScopeSet a sorted array
of distinct ScopeName values, nested records objects with exactly their fields,
and nullable parent explicitly null or a revision integer. Canonical encoding
sorts object keys lexically, uses separators comma/colon without whitespace,
ensure_ascii=False, no BOM or final newline, and UTC timestamps with exactly six
fractional digits plus Z. Decoding permits zero through six fractional digits
but requires Z, an actual valid date/time and no leap second or offset syntax.
Encode→decode preserves values; decode→encode canonicalizes spelling, not input
byte identity. Future publication/recovery must digest the actual original file
bytes when comparing a stored artifact, not a normalized re-encoding.

Both decoders reject input >131072 bytes, UTF-8/BOM errors, duplicate keys at any
depth, unknown/missing keys, floats/exponents/nonfinite numbers, trailing JSON,
wrong container types, invalid enum/nullability/revision and depth >8. Root
container depth is 1, each nested array/object adds 1. A bounded lexical scan
checks depth before the generic JSON decoder allocates a deeply nested tree;
escaped quotes/brackets inside strings do not count as structure. Digit runs
are bounded before integer conversion (signed-64-bit maximum for revision/version
fields). There is no streaming/file reader or partial-success truncation.
Unsupported integer envelope version yields UNSUPPORTED_VERSION; malformed or
missing version yields INVALID_INPUT. Encoding applies the same final byte cap.

Desktop parser retains all r2 exact endpoint compatibility values and required/
optional field sets; rejects web/extra roots/unknown fields. All URI values are
exact builtin strings. Auth/token/x509 endpoints use exact equality to the r2
allowlist, not URL normalization. Optional project_id is at most 256 ASCII bytes
with no control characters. Registration entries are distinct strings bounded
as r2: exactly `http://localhost`, or HTTP with a numeric loopback IPv4/IPv6 host,
optional decimal port 1..65535, and an optional ASCII path starting with `/`.
Reject whitespace, controls, backslash, userinfo, query, fragment, percent-encoded
host and scoped IPv6 address. Validate numeric host through stdlib ipaddress,
without DNS. Registration paths are never executed or retained; they do not
choose the fixed runtime callback. Legacy and modern metadata are accepted, but
this unit builds no library config/request; fixed modern outbound enforcement
remains the actual OAuth adapter's required positive/negative test.

### Privacy and non-authority

Parsing a disk-shaped envelope supplied as bytes proves only finite syntax and
local relationships. An attacker can construct the same model. The later manager
must still establish trusted exchange/grant provenance, accepted binding/other
account, lineage, file digest/revision, owner/receipt and publication readiness.
There is no `is_authenticated`, `is_usable`, grant attestor or implicit import.
No capability can be obtained by decoding a file or forging GrantEvidence.kind.

The explicit encode_envelope return is secret-bearing private bytes, never a
public serializer or output profile. Test positive controls must prove the
synthetic token is present in that returned memory buffer, while absent from
stdout/stderr/logs/errors/temp files and all M1-05 public serialization attempts.
Neither module installs logging hooks on import nor imports Google clients, DB,
CLI, transport, environment-discovery or file helpers. Runtime callers later use
actual M1-05 sealed bootstrap; pure code itself emits nothing even without it.
Tests exercise both import/no-bootstrap silence and real sealed subprocess exits,
including malformed private JSON and hostile repr/str/property/eq hooks.

Only this early value/codec unit may be separately accepted/integrated. Original
OA-01..20, actual M1-02/M1-03 extensions, manager publication/locks/file crash
proof, TTY callback exception, M1-05 actual auth consumer, real D3 and M6 gates
remain mandatory and pending. Structural test success cannot close any complete
OAuth, binding, startup, backup or package milestone.
