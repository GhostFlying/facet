# Interactive OAuth setup

`facet setup` is a first-run command for a new private production state root. It
authorizes source and target sequentially with the existing Desktop loopback
flow, probes each `users.getProfile`, and asks for an explicit confirmation of
the discovered role/account pair. The setup command never lists mail, reads
message content, inserts messages, writes labels, starts sync, or starts a
backfill. Source uses `gmail.readonly`; target uses `gmail.insert` and
`gmail.readonly`.

Deployment prerequisite: the target must be a newly created, dedicated Gmail
account for this projection. Before OAuth, the operator must explicitly attest
that Facet is the only application/service that will write to it; AI
agents/connectors are read-only consumers. Gmail metadata and OAuth scopes do
not prove that attestation or reveal every third-party writer. OAuth consent
itself is not a Gmail mailbox write.

The command is interactive only and requires a controlling TTY. It rejects JSON,
public/private metadata output modes, and non-TTY invocation. Use an explicit
stable request key in the existing format:

```text
facet setup --state-dir /var/lib/facet/production \
  --oauth-client /run/secrets/google-client.json --port 18080 \
  --request-id rq1_<uuid4-hex>_<uuid4-hex>
```

For a remote browser, forward the same loopback port over an already authorized
Tailscale SSH path:

```text
ssh -t -L 18080:127.0.0.1:18080 operator@sync-host
```

Run the command on the sync host (or in the setup-only Compose profile below)
with the same private state-parent mount and loopback binding. Open each
displayed Google URL in the browser using the forwarded local port. The setup
listener remains on numeric `127.0.0.1`; it is not a public listener and does
not add a Dashboard OAuth route. Keep the command's request key private.

After target OAuth and before the first projection/insert, deployment acceptance
must use read-only target checks for account binding and mailbox content across
normal mail, drafts, Spam, and Trash. An unexpected/unmanaged item, old
forwarding or spike copy, or account mismatch is a stop gate: remain blocked
and report the conflict. Setup has no delete, claim, relabel, or cleanup path;
it must not make an existing mailbox appear empty. A successful OAuth grant
does not by itself pass this target-account gate.

The supported container recipe uses an immutable image and a setup-only
loopback mapping. Set `FACET_IMAGE` to a full-commit tag or digest and provide
the Desktop client JSON through a private host path; Compose mounts it as a
read-only secret and does not include it in the image:

```sh
export FACET_IMAGE=ghcr.io/ghostflying/facet:<full-commit-sha>
export FACET_OAUTH_CLIENT=/private/path/google-client.json
export FACET_SETUP_REQUEST_ID=rq1_<uuid4-hex>_<uuid4-hex>
export FACET_OAUTH_PORT=18080
# Optional: unset defaults to 900; accepted values are ASCII digits 60..1800.
export FACET_OAUTH_CALLBACK_TIMEOUT_SECONDS=900
bash scripts/check-compose-image-ref.sh
docker compose --profile setup run --rm --service-ports facet-setup
```

Keep the host secret's parent private (`0700`) and make the secret itself a
regular, bounded, no-write file readable by the container UID (for example
`0444` or `0644`; a host `0600` file owned by another UID is not readable after
a bind mount). The container accepts the mounted secret only at the fixed
`/run/secrets/google-client.json` path, after the descriptor opens successfully;
ordinary private client paths still require owner-only ownership and modes.

The setup profile maps only `127.0.0.1:${FACET_OAUTH_PORT}` to the container
callback port and exits after setup. Inside that short-lived container only,
the explicit bind address is `0.0.0.0` so Docker can deliver the mapped
loopback connection; the host publication remains loopback-only. Direct host
invocation keeps the default `127.0.0.1` bind. The setup-only environment
`FACET_OAUTH_CALLBACK_TIMEOUT_SECONDS` defaults to 900 when unset and accepts
only ASCII decimal digits whose value is 60 through 1800. An explicitly empty,
whitespace-padded, plus-prefixed, underscore-containing, malformed, or
out-of-range value fails closed before the listener starts. The normal `facet`
service never publishes the OAuth port. It mounts the persistent parent at
`/var/lib/facet`; the
first-run `/var/lib/facet/production` child is created only after the terminal
confirmation. The default named volume is initialized for UID/GID `10001` with
mode `0700`. For a bind mount, provision the parent explicitly with numeric
UID/GID `10001`, mode `0700`, and no existing `production` child, for example:

```sh
install -d -o 10001 -g 10001 -m 700 /srv/facet
```

The container refuses mismatched ownership, modes, types, symlinks, or an
unexpected existing child before opening OAuth. It does not recursively change
host permissions. The current empty `.facet/production` development tree is
not a deployment input.

Before confirmation, interruption leaves no state or credential files. After
confirmation, local config/database/credential publication is intentional, while
Gmail message and label writes remain zero. If the process stops after local
creation, rerunning setup is refused for the existing root. Continue with the
existing per-role `facet auth authorize --role source|target --request-id ...`
commands using the recorded deterministic role keys, then inspect offline with
`facet gmail auth-status`. Do not import spike tokens, cursors, mappings, or
runtime files. Successful authorization does not start preview, backfill, or
sync; those remain explicit later commands.

This runbook documents the supported flow only. Offline fake OAuth tests do not
prove Google consent, live account ownership, deployment, or Gmail API/UI
behavior.
