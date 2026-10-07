# Explicit target cleanup review and acceptance

Base: `7b402a4d616b6db8eb262bb07ae1ce5f8732f6eb` (2026-10-07).
Owner: root implementation; independent `gpt-6.1-sol` xhigh reviewer
`/root/target_cleanup_review`.

Plan SHA256 `da94b574fe29c0b5c45b54a06cc7b8a2ae573bead9165ac1d0b0af866b586139`
approved after three bounded corrections: use immutable contained message IDs
instead of draft-container deletion; expiry gates first execution, not same-key
resume/completed replay; status is offline/query-only without writer ownership.
The subsequent plan wording correction changes "draft and message delete
requests" to "message/draft list and message-delete requests"; no behavior or
design change. Reviewer explicitly marked this correction nonblocking.

Current focused evidence: actual locked Google discovery/client with only HTTP
replaced; real CLI init/binding, preview, explicit execution, offline status and
restart recovery; wrong-account/scope/confirmation/lock/replay/failure/privacy
tests. The cleanup and existing CLI bootstrap selection passed 85 cases before
the final help-only parser correction. Final candidate review, complete checks
and non-root image acceptance are pending; do not infer live deletion or merge.

Candidate `1c502043c36ce65deefb55ae3df41b15e38658cb` received
`changes_requested`: locked httplib2 can resend DELETE after a lost response
despite Google `num_retries=0`. Reviewer reproduced two wire dispatches and
independently passed the 41 focused tests; the old fake did not exercise that
connection layer. The pre-fix full-suite run was stopped as superseded, not
counted as acceptance. No live deletion or service upgrade occurred.
Supplemental plan `ef894e55b55cd1228ae4f423785b16b469f3e223bb449ee60967b130b14f8d72`
was independently approved for a cleanup-only requests transport, with retries
and redirects disabled. Three real requests/urllib3 loopback wire cases now
cover response loss, redirects and 401; loss emits exactly one DELETE and the
same-ID GET precedes resumed work. The focused cleanup suite passed 44 cases.
Normal sync's analogous insert-transport risk remains a separate live blocker.

## Accepted current candidate

Independent reviewer approved exact
`864670323790e4000327cd724a7d0b90267c6694`, retaining the unaffected original
conclusions and independently passing the 44 focused cases. Full offline suite
on that candidate: **2697 passed in 527.26 seconds**. Locked environment sync,
repository Ruff/format, CLI help and tracked/staged safety checks passed.

The unchanged pinned Dockerfile built on sgbox and was imported locally as
`facet:8646703`, image ID
`sha256:82d9f0dee8c5a37ab1dff8c014bc24de45e74514cee5f11bdeda00815ffd4029`,
user `10001:10001`, OCI revision matching the exact candidate. The isolated
Compose project `facet-cleanup-8646703` used its own new synthetic state volume
and disabled external networking. Actual CLI init/fake authorization produced
bindings; no readiness/binding/rule/epoch rows were directly seeded.
Preview identified three unique synthetic messages, including a draft, with
zero target writes. Explicit execute injected a post-deletion response loss;
offline status retained one unknown deletion. A new container resumed via
same-ID GET and completed the fixed manifest; a later arrival survived.
Business-row/normal-credential hashes were unchanged, cleanup access-token
sentinels were absent from production files, and completed JSON replay added
zero provider calls (10 before and after). No host Python executed product
commands. Fixture mounts replaced only external Google HTTP/OAuth interactions.

The qualified local image additionally completed a real target read-only preview
under the existing binding/normal target scopes; its account and fixed IDs stay
private. Offline status read the same manifest with networking disabled. No
source request, real mailbox mutation or full-scope OAuth was performed.

CI, main integration, publication and live-service upgrade are not claimed.
The normal insert transport remains a known separate blocker. The subsequent
live authorization and evidence are recorded below, separately from engineering
acceptance.

No real deletion, expanded persistent credential, source mutation, normal-state
reset or unknown insert retry is authorized by this engineering receipt.

## Separately authorized controlled live cleanup

On 2026-10-07 the user approved the actual 134-message fixed preview and
completed separate ephemeral target full-mail OAuth. The first consent wait
expired without destructive dispatch; the same execution key and manifest were
resumed with fresh consent, not a new preview or expanded scope. The qualified
local image exited successfully. Offline receipt: completed, 134 confirmed
absent, zero remaining and zero unknown deletions. A subsequent normal-scope
read-only target profile/list check verified the bound account, zero messages
including Spam/Trash, zero drafts and no next pages.

Before execution a fresh private SQLite API backup included the main DB,
maintenance journal, config and normal credentials; both database integrity
checks passed. Read-only comparison afterwards found all main business rows
unchanged except writer-owner lineage, plus unchanged config and normal
credential files. Existing unknown inserts remain one and mappings remain zero.
No source request, send, new-arrival deletion, persistent full-scope credential,
DB reset, unknown-insert retry or daemon restart occurred. Real account/manifest
identifiers and OAuth materials remain outside this public receipt. Deleted
Gmail content cannot be recovered from the metadata backup.
