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

No real deletion, expanded persistent credential, source mutation, normal-state
reset or unknown insert retry is authorized by this engineering receipt.
