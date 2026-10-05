# OAuth-first CLI setup

Date: 2026-10-05. Revision: 1. Status: awaiting independent plan review.
Base: `a05499acd36c67db7fcb42617cdd4ca1438ee4b6`.

## Outcome and scope

Add interactive `facet setup --oauth-client <private-desktop-client> --port
<loopback-port> --request-id <request-key>` for a new production state directory. The user chooses source
and target Google accounts sequentially; `users.getProfile` discovers their
addresses. A final terminal prompt shows both actual addresses with their roles
and requires an explicit confirmation before creating config, bindings, or token
files. No expected-address arguments are needed. Preserve existing `init` and
role-specific `auth authorize` behavior.

Only a Desktop-client JSON may be reused from an exploratory setup. Never import
spike tokens, cursors, mappings, or runtime state. Offline tests use only
synthetic OAuth/Gmail transport and do not read real client material or contact
Google. The shipped non-fake command retains live loopback OAuth/profile calls
under the existing external authorization boundary. Neither path deploys, starts
sync/backfill, lists mail, fetches raw, inserts messages, or mutates labels.
Default scopes remain source `gmail.readonly` and target
`gmail.insert` plus `gmail.readonly`; no mode/scope widening option is added.

## Files and phases

- `src/facet/cli/bootstrap.py`: parser and dispatcher, small setup handler using
  existing config serializer, private path checks, `StateOwner.create`, config
  publication and durable per-role authorization operations.
- `src/facet/gmail/oauth.py`: add an explicit strict first-run/setup mode to the
  existing authorizer. This mode disables incremental consent and requires the
  provider's actual granted-scope evidence; the existing role auth path keeps
  its current behavior and interface by default.
- `tests/unit/test_gmail_oauth.py` and `tests/cli/test_setup.py`: strict-scope,
  interactive dispatch, and production owner/manager tests.
- Optionally `src/facet/cli/setup.py` if a focused module keeps bootstrap smaller;
  no new runtime framework, schema, journal, dependency, callback or Web route.
- `tests/cli/test_setup.py`: production CLI dispatch with fake interactive streams
  and only external OAuth/profile transports replaced; real owner/manager/DB.
- `docs/cli-spec.md` (interactive setup contract), `docs/oauth-setup.md`, a
  concise README entry, this plan and delegated
  `docs/development-status.md` handoff: supported SSH/Tailscale setup, phases,
  safe restart guidance and exact offline evidence.

1. Validate flags, port, projection and mandatory interactive stdin/stdout/stderr.
   Refuse `--public`, `--json` and non-TTY before external calls; `--yes` never
   skips discovery confirmation. Reject explicit alternate config paths. Resolve
   the root with the existing path helper; refuse any existing root (including
   empty roots) before OAuth. Require an existing parent; do not modify it.
   Setup requires `--request-id` in the existing `RequestId` grammar
   `rq1_<uuid4-hex>_<uuid4-hex>`. The caller establishes and records this key
   before OAuth. Role authorization keys are deterministic
   `_auth_role_nonce(setup_nonce, role)` UUIDv4-shaped values, displayed
   alongside the role before publication. Replays use the same exact keys; a
   mismatched key/payload is a request conflict.
2. Read the private Desktop client through the existing no-follow bounded loader.
   Exchange source then target OAuth on the same `127.0.0.1` listener/localhost
   redirect port. First-run setup must not request incremental consent
   (`include_granted_scopes=true` is removed for this path), and the adapter must
   take the provider's actual `granted_scopes` token response when present. An
   absent scope response is unknown and fails closed; it is never filled from
   requested/configured scopes. Probe only each role's `getProfile`. Hold typed
   secrets and profile facts in memory. Reject expired credentials, actual grants
   unequal to the fixed role policy, invalid profiles and identical normalized
   accounts. Existing role-specific reauth may retain its reviewed scope-lineage
   fallback, but setup cannot import or union prior spike grants.
3. Build the default config from those discovered profiles and validate it before
   printing addresses. Explain source read access, target insert/read access,
   target unmanaged content risk, and that setup does not start copying. Require
   the explicit word `confirm` on the terminal; decline/EOF/interruption leaves
   no root, config, DB, readiness, or tokens. Secret objects keep sealed reprs.
4. Recheck absence immediately before creation. Call `StateOwner.create` directly
   (never the replay-capable init path for an existing root), write config through
   the current atomic helper, retain this owner through both role publications,
   and call `CredentialManager.authorize_role` with each original grant and
   profile fact. The manager's production profile probe must still recheck the
   account during validation, so changed accounts fail against confirmed config.
   Create/complete operations through the existing command store with separate
   stable per-role nonces, established before publication. No transaction spans
   network waits. Return only aggregate initialized/binding state. “Zero writes”
   means zero Gmail/message/label writes; local DB/config/credential publication
   is the intentional setup effect after confirmation.

## Failures, recovery and privacy

Before confirmation there are no durable artifacts. State creation after
confirmation is exclusive, so another setup winning the race is refused without
adopting or overwriting its state. Once initialized, failures retain the private
pending state instead of rolling it back or reinitializing; incomplete role
publication cannot make both roles ready. Normal existing `auth authorize
--role ...` and offline `gmail auth-status` are the continuation paths; validated
credential changes and ambiguous outcomes remain governed by existing manager
and operation guards, with maintenance-required states reported honestly.
Config-publication failure retains bootstrap evidence; recovery uses the
existing init request/config replay procedure, never an empty-DB shortcut. If
setup is interrupted after creation, do not restart the wizard: use the caller's
recorded private bootstrap key and deterministic role keys with the existing `auth
authorize --role source|target --request-id ...` commands. A setup rerun against
that root refuses before OAuth; continuation never starts sync. Document the
local bootstrap and role request keys needed for recovery; these may be shown
only in the explicit private terminal flow and never public JSON.
Addresses and OAuth URLs are confined to interactive setup. Final CLI output,
errors, logs and tests must not expose accounts, paths, secrets or provider text.

## Acceptance

- New setup binds two discovered distinct accounts through real initialization
  and credential manager without DB seeding, keeping default production config.
- Decline, EOF, same account, scope mismatch, profile failure, invalid port,
  existing root and JSON/public/non-TTY guards leave no new durable state and
  never start mail operations. `--yes` still requires final explicit confirmation.
- Sentinel credentials/provider errors never appear in stdout/stderr/results;
  only the deliberate interactive account confirmation contains addresses.
- Failure between source/target publication retains pending target and cannot
  run a production provider cycle; a restarted per-role auth completes the
  existing state without replacing source/bindings or adding readiness manually.
- Tests replace only external OAuth/Gmail transport; the production command keeps
  live loopback OAuth/profile calls behind the existing authorization boundary.
  Reuse the fake external Gmail CLI vertical path where practical for rule,
  preview, explicit start, run/readback/mapping and restart evidence.
- Run focused CLI/OAuth/credential tests, full offline pytest, Ruff lint/format,
  both CLI help checks and repository safety; publish no real OAuth evidence.

The OAuth adapter test must assert the strict setup authorization request omits
incremental scope union and that `granted_scopes` is selected over any
requested-scope property. In strict setup mode, a fake response without actual
`granted_scopes` must return `scope_required` even when `credentials.scopes`
contains the requested scopes. Existing non-setup authorization tests retain
the old compatibility behavior.

## Runbook and stop gates

Use a same-port SSH forward over a Tailscale host, e.g.
`ssh -t -L 18080:127.0.0.1:18080 operator@sync-host`, then setup with port 18080
and a fresh child state root. A Linux one-off image invocation may use host
networking for this short-lived loopback listener while retaining the image's
non-root UID and private mounts. The daemon remains stopped during setup; no
public listener or Dashboard OAuth is introduced. Documentation must distinguish
offline code evidence from live OAuth/container/deployment gates.

Stop for a required new scope, callback/external service, privacy-contract
change, existing-state adoption, or credential recovery behavior outside the
shipped manager protocol. The independent reviewer approves this exact plan
revision before production code. Implementation gets a separate exact-candidate
independent review and CI before integration. This unit closes no live Gmail,
deployment or Phase 1 milestone gate.
