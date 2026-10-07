# Explicit dedicated-target cleanup

This is an operator-invoked maintenance command, never a sync prerequisite that
silently deletes mail. It permanently removes only the target message IDs in an
approved preview, including Spam, Trash and the preview's draft-contained
messages. It does not send mail or touch source Gmail. Edited/sent draft
replacement messages and new arrivals are not included.

## Before starting

Stop the sync container and retain an owner-only SQLite backup (SQLite backup
API, not just the live main file) plus config/bindings/normal credentials.
Preserve the maintenance journal with state backups too. A metadata backup
cannot restore deleted Gmail content. Review `existing_mappings` and
`unknown_inserts`: deletion can remove recovery evidence, but never resets those
rows, authorizes another insert or resumes sync. Do not proceed without separate
approval of the actual preview for live operations.

Sync keeps `gmail.insert` + `gmail.readonly`. Permanent deletion requires
`https://mail.google.com/`, whose actual authority also includes reading and
sending. The cleanup process requests it separately with online access, no
incremental union, and validates the actual grant. Its access token stays only
in memory; no refresh token or broad sync credential is saved. Wrong-account
consent fails before deletion. "Temporary" describes Facet's token handling,
not an automatic expiry/revocation of the account's consent record at Google.
Do not automatically revoke the application grant: that can also disrupt normal
authorization. [Google message deletion API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/delete).

## Commands

Choose and privately retain separate UUID4 hex request keys before starting.
Commands run from the same Compose image/state volume; no host Python is needed.
Replace uppercase placeholders with the operator's private values, never commit
them. Keep the OAuth client mounted read-only as for normal setup.

```sh
docker compose stop facet
docker compose run --rm --no-deps facet target-cleanup preview \
  --state-dir /var/lib/facet/production --request-id PREVIEW_REQUEST_KEY --json
docker compose run --rm --no-deps facet target-cleanup status \
  --state-dir /var/lib/facet/production --preview PREVIEW_ID --json
```

Preview lists metadata IDs only, with full pagination; output is exact unique
message/draft counts, existing-mapping/unknown-insert warnings, a local preview
ID and expiry. It performs zero Gmail writes. It is not an atomic Gmail snapshot:
the saved fixed IDs, not later mailbox contents, define the deletion scope.
First execution must start within 30 minutes; an expired unused preview needs
a new request key/preview and approval. Status is query-only and works without
Gmail or a writer lease. There is no Dashboard cleanup/OAuth endpoint.

After approving the actual preview, use an interactive terminal:

```sh
docker run --rm -it --network host \
  --mount type=volume,source=STATE_VOLUME,target=/var/lib/facet \
  --mount type=bind,source=/PRIVATE_DEPLOY_DIR/google-client.json,target=/run/secrets/google-client.json,readonly \
  IMAGE_SHA_OR_DIGEST \
  target-cleanup execute --state-dir /var/lib/facet/production \
  --preview PREVIEW_ID --request-id EXECUTION_REQUEST_KEY --yes \
  --confirm-target TARGET_ADDRESS --oauth-client /run/secrets/google-client.json \
  --port 18082
```

The callback binds loopback. The one-off host-network container above has no
Dashboard listener and uses the exact same state/secret mounts and image as
Compose (substitute those explicit deployed values). Ordinary bridge port
publishing cannot reach a container-loopback OAuth listener. Do not expose
OAuth or the Dashboard on a public interface. SSH local
forwarding must preserve the same port at the browser and callback host. The
URL is printed only to the controlling terminal, never JSON/logs/reports;
`--yes` cannot bypass this interaction or select a different target account.
`--public` is unsupported for these private maintenance commands.

Deletion uses `messages.delete` with no automatic retries. After interruption,
repeat the same execute command/key/confirmation; fresh temporary OAuth is
required. Unknown deletions are first checked with an ID-only `messages.get`:
absent is confirmed, present can be deleted under the original fixed approval,
ambiguous network/auth failures remain unresolved. Started executions may
resume after preview expiry; changed binding/config blocks further deletion.
Completed replay returns the existing receipt without OAuth/delete and can be
noninteractive. Do not change keys to manufacture another execution.

Completion means only the approved IDs are confirmed absent, not that the
current mailbox is empty. Recheck the dedicated-target prerequisite separately.
Do not delete new arrivals automatically, reset state, claim unmapped mail or
retry unknown inserts as part of cleanup.
