# Drain the existing selected queue

2026-10-08. User explicitly authorizes continuation on the original accounts,
rules and fixed window, then final checks. Base main `f5f39c849cbd9342c83ec7555955e0624ce979d1`;
reuse accepted source/image `1a8eef14937caf8f58bc8035eb964e3b7bcec38f`.
Root executes; independent Sol xhigh reviews the bounded operator change.

No production implementation, schema, configuration, rules or scope changes.
Only extend the existing private `auth-continuation.py` with ordered `drain1`–
`drain3` one-cycle phases and extend its existing sample selector accordingly.
Each phase requires a completed clean predecessor and exact unchanged saved
business snapshot, saves its submission before invoking production `run --once`,
and refuses replay after completion, failure or response loss. Legacy receipts
remain untouched. Reuse existing continuation-result guards and atomic journal.

Before copying: verify source/image equivalence and stopped service, private
writer-locked SQLite/config/credential backup, normal production startup role/scope
checks, and fresh read-only target classification. If access tokens have expired,
call existing production `prepare_credentials` under `StateOwner` before inspection;
this manager-owned refresh/profile verification runs no History, discovery,
projection or recovery and does not change the saved business snapshot.
After every successful cycle,
classify target and sample up to 20 mappings added by that exact phase before the
next phase. Finish once selected historical work and ordinary projection queued/
retry work are drained; a quiet restart must make no duplicate insert. Three
bounded phases are a guard, not an unbounded daemon. If work remains, report it.

Pure synthetic tests cover ordering, changed baseline, incomplete/unclean receipt,
marker-before-dispatch, submitted-phase replay refusal, lost-response/persistence
failure, and exact-phase sample selection. Review binds private file hashes;
no private state/mailbox access by reviewer. No repeated source qualification.

Stop on new uncertain insert, auth/scope failure, unmanaged target content,
new unsafe attention/failure, or failed protected-state invariant; retain submitted
receipts, never auto-resubmit. Old unknown/attention/blocked work and stopped
generations remain protected, not counted as successful or silently removed.
No preview/start, new epoch/window/rule, source mutation, send/delete/cleanup,
unknown retry, permanent service, deployment or Release. Raw only in bounded RAM;
public evidence is aggregate-only. Final target/sample, zero-claim/protected-state
checks and private backup precede concise current-status/receipt documentation.

## User-authorized action-label check during continuation

The user subsequently authorizes adding configured AddSender/AddDomain labels
during the current copying pass, then checking the next cycle's learning and the
current cycle's isolation. `drain1` keeps its original unchanged-rule guard.
For `drain2`/`drain3` only, extend the same private operator to capture a separate
private metadata snapshot before/after invocation: immutable configuration/bindings/
action-label mapping, current rule row digests and kinds/origins, and action-command
row metadata/digests. Original current rules must remain unchanged; additions must
be enabled action-label-origin allow-sender/domain rules, bounded by newly executed
AddSender/AddDomain commands of the corresponding kind. No CLI rule modification,
blacklist, account/scope/configuration change or new historical epoch is permitted.
Only after these checks may the old scope hash's rule-only delta be accepted by
the existing mapping/unknown/stopped/epoch/job guards. Save the learning evidence
in the existing submitted-phase receipt; output only aggregate counts.

Focused pure tests cover valid sender/domain learning, wrong origin/kind, modified
prior rule, immutable configuration/binding/label-map change, unsupported action,
missing executed action and unchanged-rule idempotent activation. Exact candidate
hashes need independent affected review before dispatch. This does not alter
production code or automatically backfill other domain/sender historical threads.
The selected labelled thread's complete non-draft history is the authorized action
disclosure. Final checks distinguish learning, selected-thread projection and
historical drain; changing rules is intentional only under this user addendum.

The existing private backup helper's one-sender precondition also needs a bounded
adjustment after authorized learning: accept the exact enabled-kind list from
the last clean actual snapshot (sender/domain only), retain old-unknown checks,
and print actual aggregate counts. Its SQLite-API/credential/owner-only copy path
stays unchanged. Pure precondition checks and affected independent review are
required; no CLI backup implementation or runtime redesign is introduced here.
