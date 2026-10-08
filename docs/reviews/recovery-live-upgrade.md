# Existing test deployment: bounded upgrade and diagnosis

2026-10-08. The user explicitly requested updating the existing real deployment
and checking remaining unhandled work. No new accounts, OAuth scopes, rules,
historical window, mailbox cleanup or unknown retry were selected.

## Reviewed procedure and artifact

Independent Sol xhigh approved the operational plan SHA256
`e65296cf38c51e866ca46964e3f2c727fdd8a48c0f3c86de096f96ae35dda9c6`
and the final private operator helper SHA256
`53220eefa137519520919b9657a9bf9b6b757efcde8f50ef2ee5de9fdd9481df`.
Affected review verified SQL/API interfaces and synthetic submission-before-dispatch,
thirteen valid closures and retained-attention mutation rejection. Root verified
syntax/image imports and read-only production snapshots without Gmail access.
The helper composes the accepted backup/snapshot/actual CLI operations; it does
not implement sync business work or directly repair rows.

Installed image: `ghcr.io/ghostflying/facet:42c586ff1456e919a6c97ab3b434c5a18666b835`.
Published index: `sha256:f8343daef2211209af8150ff93d616dac5802a8367cc1cfc2e01a980fd091b89`.
Imported amd64 image: `sha256:8f9cc6b44132c1e7546273c0faf15def034f196d1535c09a1ef5a87dc87dcdc7`.
Anonymous pull through the already-authorized jump path passed; local image ID
matched, UID is 10001:10001 and 112 source files matched the merged commit byte
for byte. Main image publication and offline checks passed. Published images lack
the OCI revision label: build commit/digest and actual source-byte evidence were
used instead. No fresh platform-manifest inspection is claimed; the jump host's
older Docker inspection tooling failed. Existing qualified rollback image and
prior deployment configuration were retained, never substituted during the run.

## Actual production result

Writer-locked SQLite backup (including WAL), config/credentials and cleanup journal
passed integrity/private-permission checks. Compose was recreated without starting
a perpetual service. A private durable marker preceded exactly one actual image
CLI `run --once`; there was no resubmission and no overall insert-killing timeout.

The cycle completed in 26.37 seconds: one History page, 19 resolved events,
three verified projections, zero new attention and zero warnings. Mappings rose
4306 to 4309. Old attention dropped 58 to 45 through exactly 13 proven resolver
closures; other old attention remained unchanged. Previous mapping rows,
account/rule scope, stopped generations, epoch discovery and label configuration
were preserved. All three new attempts were verified and mapped; no old unknown
source was resent. The single old unknown retains certainty unknown, attribution
none and `insert_result_unknown`, with one completed check and a new deadline.

## Remaining diagnosis and boundary

Read-only source metadata/current-rule evaluation found 17 unresolved message-added
events: 11 no-rule, six currently eligible. Remaining label events are nine system
removals, four configured-action removals, four configured-action additions and
eight unknown/retired-label additions/removals. Three projection jobs depend on
the old unknown. These are events/dependencies, not 45 distinct failed messages.
One effective configured action label currently exists in source; local action
configuration was preserved and no source label was created. Diagnosis performed
zero Gmail writes and zero business replay; credential ownership/profile/scope
guards remained active. No raw content was persisted or exposed.
Fresh read-only target enumeration/classification found 4309 mapped items, two
permitted source-From SENT items, zero drafts and zero other unmanaged items.
A post-run writer-locked backup passed at the new 4309/45/one-unknown state.

The unresolved events were not broadly retried. Current eligibility does not mean
the six events have been admitted/projected; action additions still need deduplicated
consumer processing. Unknown label identity is not guessed. Empty unknown search
does not establish ownership or authorize resend. Continuous Compose service remains
stopped. A stale pre-run DB must not be restored after the three real inserts;
rollback keeps current durable state. No Release/full Phase 1 acceptance is claimed.
