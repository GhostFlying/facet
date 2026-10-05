# Container deployment and OAuth setup verification

Date: 2026-10-05. Revision: 3. Status: awaiting independent plan review.
Base: `b139ca94564cc4fb439fcd6e759585c8b1572df4`.

## Goal

Make the supported first-run OAuth path usable from the non-root Compose image
without weakening the private-state or output boundaries. The image and
Compose example must use an immutable image reference, keep one non-root
foreground owner on a persistent state path, and expose the Desktop client only
through a read-only secret mount. Setup must finish all local preflight checks
before opening a browser or making an OAuth request. Mounted-state checks must
validate the final container-visible root rather than rejecting a trusted host
path merely because an ancestor such as `/data00` is owned by another host
account.

This unit is offline and synthetic. It does not run OAuth, copy a real client
secret, change broad host permissions, publish an image, or deploy Compose.
The existing empty `.facet/production` tree remains untouched.

## Scope and files

- `Dockerfile`: retain the pinned Python base and UID 10001, create only the
  container-visible `/var/lib/facet` parent with owner-only permissions, and
  keep the image free of config, token, client, production-child, and spike
  data. The entrypoint remains the single `facet` process. The setup command
  receives `/var/lib/facet/production` as a new child and may create it only
  after its preflight and final confirmation; the normal service reuses that
  child on later starts.
- `docker-compose.yml`: use a required `FACET_IMAGE` immutable tag/digest with
  `pull_policy: never`, mount the persistent state parent at `/var/lib/facet`
  (with the production child created by setup), mount a read-only
  synthetic/documented Google
  Desktop client secret at `/run/secrets/google-client.json`, and provide a
  setup-only Compose profile. The setup profile maps only
  `127.0.0.1:${FACET_OAUTH_PORT:-18080}` to the same container port and is run
  with `docker compose --profile setup run --rm --service-ports facet-setup
  ...`; this is the exact callback path for the browser/SSH forward. The
  normal `facet` service never publishes the OAuth port and keeps only its
  host-loopback Dashboard port. Preserve read-only root, `/tmp` tmpfs, and
  non-root UID 10001. No default public ports or implicit backfill.
- State provisioning is explicit. The setup and normal services mount their
  parent at `/var/lib/facet`; the default named volume is initialized from the
  image's parent directory (UID/GID 10001, mode 0700) with no `production`
  child, so first-run setup can create the child after confirmation. A bind
  mount is supported only after the operator creates the host parent with
  numeric UID/GID 10001 and mode 0700 and leaves its `production` child absent
  (for example, `install -d -o 10001 -g 10001 -m 700 "$FACET_STATE_DIR"`).
  Failure to provision, an existing unexpected child, or a mismatched final
  root fails before OAuth. No recursive `chmod`/`chown` is performed, and the
  existing empty `.facet/production` directory is not touched by tests or this
  unit.
- `src/facet/gmail/oauth.py` and, if needed, the setup path in
  `src/facet/cli/bootstrap.py`: make the client-file reader accept the exact
  container secret contract (no symlinks, bounded regular file, no writable
  group/other bits, and readable by the service UID) while retaining strict
  owner-only checks for ordinary private files. Setup validates state-root,
  config, parent/mount, request, TTY, port, client readability, and all
  required local prerequisites before the first authorizer call. A preflight
  failure leaves state and credentials absent and produces only a fixed error.
  The final mounted state root and its immediate private children are checked
  by descriptor/type/UID/mode; ownership of unrelated host ancestors (for
  example `/data00` or `/run`) is not treated as state ownership evidence and
  cannot reject an otherwise valid container mount. The client secret uses the
  separate read-only container-secret contract: no symlink, bounded regular
  file, no group/other write bits, and readable by the service UID; ordinary
  host private files retain owner-only validation.
- `tests/unit/test_gmail_oauth.py`, `tests/cli/test_setup.py`, and a focused
  container/Compose test module: synthetic mounted-secret and state-root
  fixtures, final-root ownership/mode checks, trusted host-ancestor fixtures
  (including a synthetic `/data00`-shaped path), preflight-before-authorizer
  assertions, no-state-on-failure checks, Compose YAML/image/mount/UID/static
  privacy checks, and no network/provider calls. Tests must never inspect or
  copy `.facet/production`, HOME credentials, or real OAuth material.
- `docs/oauth-setup.md` and a concise deployment runbook section: document the
  two-phase workflow (`docker compose --profile setup run --rm
  --service-ports facet-setup ...` with a mounted secret, then `docker compose
  up -d`), local loopback/SSH forwarding, `/var/lib/facet/production`,
  named-volume versus explicitly provisioned bind ownership/mode expectations,
  immutable `FACET_IMAGE`, the exact setup-profile loopback mapping, and
  explicit stop gates. State clearly that offline tests do
  not prove Google consent, mailbox ownership, live Gmail, image publication,
  or host deployment.

## Acceptance tests

1. Compose config validation proves the required immutable image variable,
   `pull_policy: never`, non-root UID, state-parent mount with an absent
   production child before setup, read-only
   client-secret mount, no secret bytes in the image, setup-only loopback
   callback mapping, no persistent OAuth listener, and no implicit `backfill
   start`.
2. OAuth client loading accepts a synthetic read-only mounted secret whose
   parent is a trusted system/container directory, rejects symlinks,
   writable modes, wrong type, oversize data, and malformed/unknown JSON, and
   never includes client or token sentinels in errors, logs, or normal output.
3. Setup preflight tests prove every invalid state-root, config, TTY, port,
   request, secret, and final-root condition is detected before the fake
   authorizer is called; no state, DB, credential, or pending OAuth artifact is
   created on failure. A final mounted root under a host-like `/data00`
   ancestor is accepted when the container-visible root itself is owned and
   private. The named-volume fixture proves the parent UID/GID 10001 and mode
   0700 with no pre-existing production child; a bind-parent fixture proves a
   mismatch or pre-existing unexpected child fails without changing
   permissions.
4. The focused tests, offline full suite, Ruff/format, package/wheel smoke,
   and `bash scripts/check-repo-safety.sh` pass. Docker daemon/build and live
   OAuth checks are recorded only when externally available and are not
   claimed by this unit.

## Risks and stop gates

- Do not broaden OAuth scopes, add Dashboard OAuth, persist raw/client/token
  material outside manager-owned paths, or relax no-follow and final-root
  ownership checks. If Docker's secret UID/mode behavior cannot satisfy the
  exact reader contract, stop and report the smallest contract decision.
- Do not use a host path, real Google client, real account, OAuth browser,
  network, registry, image publication, host deployment, permission rewrite,
  or `.facet/production` contents as test evidence. No live operation is
  authorized by this plan.
- If existing CLI ownership/credential persistence needs a schema or lock
  change, stop and revise this plan before coding. Implementation begins only
  after independent review by `/root/cli_sync_review`; after coding, provide a
  candidate SHA for independent implementation review.
