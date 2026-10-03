# M1-04 credential refresh and verified adapter seam

Status: implementation plan for independent review.  Base: `fcb7afbb1df9e139d5eb33ccfd4a80b4156b84c8` (current `origin/main`).

## Goal

Complete the narrow offline M1-04 consumer required by the first M2 product path:
owner-only source/target envelope files, profile/account/scope/role/revision
verification, an immutable access snapshot for the Gmail adapters, and a
serialized synthetic refresh path.  This does not perform OAuth, call Gmail, or
claim live account evidence.  It supports only the Docker foreground single
owner model; no daemon/IPC/capability framework or host-runtime compatibility is
introduced.

## Existing API failure and minimal persistence change

The current `CredentialManager` can read fixed `0600` role files and publish the
initial `VERIFICATION_PENDING -> VERIFIED` binding.  `verify_bindings` rejects a
changed `credential_revision` after a row is already `VERIFIED`, and there is no
durable refresh phase/digest.  Replacing a token file alone would therefore make
restart state ambiguous: the file could contain a newer token while SQLite still
authorizes the old revision, and a concurrent refresh could overwrite it.

Add one typed `credential_changes` table to the fresh-v2 catalogue (not a new
runtime/schema version or a second database).  It stores only role, kind/phase,
old/new and binding/policy revisions, operation/supersession IDs, exact envelope
digest, bounded grant metadata, profile/expiry timestamps, and controlled error
code.  A unique unresolved-role guard plus repository CAS operations enforce one
writer-owned change at a time.  The existing binding update remains the source
of accepted revision; refresh publication updates it only in the same writer
transaction as the committed change.  No token/client secret/provider response
is stored in SQLite.

## Owned files and interfaces

- `src/facet/gmail/credentials.py`: fixed-path no-follow reader and atomic
  owner-only writer; `AccessSnapshot`, typed profile verification, per-role
  mutex/single-flight refresh callback, revision and binding checks.  The
  callback receives/returns private typed values only; no provider object is
  retained or refreshed implicitly.
- `src/facet/gmail/credential_models.py`: add the private change/snapshot value
  records required by the manager; preserve existing finite exports/validation.
- `src/facet/db/migrations/v0002.py`, `src/facet/db/migrations/__init__.py`,
  `src/facet/db/schema.py`, `src/facet/db/models.py`,
  `src/facet/db/repositories/serialization.py`: extend the trusted fresh-v2
  catalogue/typed row codec with `credential_changes`.
- `src/facet/db/repositories/credentials.py` and
  `src/facet/db/repositories/bindings.py`: begin/validate/commit/abandon
  metadata CAS and verified refresh revision publication; all SQL is fixed and
  runs through the existing `UnitOfWork`.
- `tests/unit/test_credential_manager.py`,
  `tests/unit/test_db_credentials.py`, and focused additions to existing schema
  tests: synthetic file permissions/symlink/atomic-replace faults, profile and
  scope mismatch, concurrent same-role refresh single-flight, stale revision,
  commit failure/restart attention, and absence of token/provider values in DB,
  logs, reprs, and test output.  Tests use fake exchanges only and never Gmail.

## Acceptance and stop gates

1. Existing full suite remains green; fresh owner state opens with the exact
   extended manifest and current binding/action/backfill behavior unchanged.
2. Source/target files are fixed beneath the verified state root, regular,
   owner-only, `0600`, no-follow, bounded, and atomically replaced through a
   same-directory temporary file; unsafe objects fail closed without chmod or
   arbitrary cleanup.
3. Startup/profile verification checks both distinct configured accounts,
   exact role/policy/granted scopes, state/projection/binding/credential
   revisions, and publishes only closed metadata.  `AccessSnapshot` contains
   only the access token plus role/revision/expiry metadata and has a sealed
   representation.
4. A same-role refresh serializes, persists requesting/validated/committed (or
   controlled attention) metadata, never serves an uncommitted candidate, and
   cannot overwrite a newer revision.  Other-role work remains independent;
   network callbacks run outside SQLite transactions.
5. Injected file/fsync/replace/DB-CAS failures retain either the previous
   accepted state or a durable attention state.  Restart never guesses a
   successful refresh, adopts an arbitrary credential file, retries OAuth, or
   clears jobs/unknown insert state.

Implementation stops and returns to root if the existing v2 manifest cannot be
extended without invalidating accepted migration evidence, if a repository
extension would require direct SQL outside the owner transaction, or if the
manager would need to expose secrets to public/status/adapter DTOs.  Live OAuth,
real Gmail profile/refresh, CLI loopback, backup/restore, and deployment remain
separate gates.
