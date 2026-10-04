# CLI sync closure

Date: 2026-10-04. Status: implementation candidate in focused verification.

## User-observable next delivery

From a clean private state directory, a production `facet` subprocess must be
able to initialize the projection, complete an explicit synthetic OAuth/profile
binding command for both roles, preview and explicitly start discovery, run one
foreground cycle against fake Gmail, and report an aggregate receipt. A second
process invocation must continue from durable state: it must consume the saved
History/epoch position, preserve mappings, and never blindly repeat an unknown
insert.

## Current facts

- Reusable now: `facet init`, managed config integrity, `StateOwner`/single
  writer, credential envelope/verification and snapshots, Gmail source/target
  adapters, `BackfillProducer` preview/start/discovery primitives,
  `ForegroundSync`, durable jobs/events/H0/intent/mapping repositories, and the
  reviewed runtime composition seam.
- Missing on the product path: a production OAuth/binding CLI command with an
  injectable fake authorization transport; persisted rule loading into a real
  `AdmissionEvaluator`; CLI commands for preview/start; `run --once` dispatch
  that constructs the verified runtime; source discovery candidate production
  including real source-path attestation; and a subprocess restart test that
  drives all of those commands rather than seeding readiness in the database.
- The current `run --once` is intentionally preflight-only. The runtime seam
  has no CLI consumer yet. This is the immediate integration gap, not a reason
  to add another abstraction layer.

## Convergence and de-scoping

One implementation path will own OAuth/binding, persisted rules, preview/start,
runtime dispatch, and the fake-Gmail subprocess harness. Keep raw mail in memory,
unknown authenticity in attention, preview write-free, explicit backfill start,
durable ordering, unknown-insert recovery, stopped generations, single writer,
credential ownership, account/scope checks, and aggregate-only output.

Move out of this path: generic capability/runtime frameworks, daemon/IPC/request
receipt work, native/bootstrap defenses outside the supported Compose image,
parallel scheduling/raw-budget tuning, Dashboard/Compose/Actions polish, and
unrelated maintenance commands. They remain later milestone work unless a
concrete current-path failure proves otherwise.

## Acceptance and authority boundary

The candidate must pass focused tests, the complete offline suite, CI, privacy
scan, and a subprocess E2E using only fake OAuth/Gmail transport. The fake may
replace provider interactions but may not write credentials, verified bindings,
rules, epochs, or readiness directly to SQLite. Real Gmail account selection,
scope changes, live writes/repair, deployment, and release remain separately
authorized. Automatic admission must use a real source-path attestation
producer; fake evidence is test-only and cannot close that live gate.

This is a minimal revision to the next execution-plan ordering, not a new Phase
1 contract or a waiver of M1–M6 acceptance gates.

## Candidate evidence and remaining gap

The current candidate implements the fake-only authorization command, exact
sender rule command, write-free preview, explicit start, persisted ruleset
loading, and `run --once --fake` runtime dispatch. A clean subprocess path has
passed init → authorize → rule → preview → start → run twice: the first run
discovered one synthetic thread, completed one insert/readback and one durable
mapping; the second run projected zero new messages. The same behavior is
covered by `tests/cli/test_bootstrap.py` without database readiness seeding.

This does not close live automatic admission. The non-fake authorization path
still returns `source_auth_required`, and the fake runner uses test-only source
attestation evidence. A real OAuth flow and verified Gmail source-path
attestation remain the next external/provider-bound implementation gap.

### Minimal candidate revision after implementation review

Before acceptance, all four mutating CLI steps must honor the existing stable
request-key contract on replay: authorization returns the already verified
result, rule insertion returns the original ruleset revision, preview returns
the original preview, and start returns the original epoch while preserving
the original fence. The fix is limited to typed request lookup/replay and a
small owner-scoped resume helper; it does not add a generic command framework
or change the product path. Raw SQL remains behind that fixed internal helper,
and no provider or live-account authority is added.
