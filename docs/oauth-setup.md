# Interactive OAuth setup

`facet setup` is a first-run command for a new private production state root. It
authorizes source and target sequentially with the existing Desktop loopback
flow, probes each `users.getProfile`, and asks for an explicit confirmation of
the discovered role/account pair. The setup command never lists mail, reads
message content, inserts messages, writes labels, starts sync, or starts a
backfill. Source uses `gmail.readonly`; target uses `gmail.insert` and
`gmail.readonly`.

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

Run the command on the sync host (or in a short-lived setup container with the
same private state mount and loopback binding). Open each displayed Google URL
in the browser using the forwarded local port. The setup listener remains on
numeric `127.0.0.1`; it is not a public listener and does not add a Dashboard
OAuth route. Keep the command's request key private.

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
