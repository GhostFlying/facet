# M2 Adapter, Discovery and Normal History Implementation Plan

Status: implementation plan for the bounded M2 producer unit, carried on
`fcb7afbb1df9e139d5eb33ccfd4a80b4156b84c8`.

## Scope

Implement the narrow Gmail-shaped source/target adapter with an injected fake
transport boundary, and the producer paths for the fixed six-calendar-month
discovery epoch and normal History pagination.  The producer consumes the
shipping profile/binding verification and PR33 operation/epoch repositories;
all source events and derived expansion/message jobs are durable before a
History cursor or discovery partition is advanced.  Typed event/job keys make
replayed pages and labels idempotent.

Files are limited to `src/facet/gmail/`, `src/facet/projection/` and focused
tests.  No spike imports, generic provider registry, target projection worker,
History-404 recovery, scheduler/concurrency, daemon/IPC, Dashboard, CLI polish,
Compose, or raw disk cache are included.

## Acceptance tests

- Adapter profile, discovery, History, message/thread metadata, raw retrieval,
  target insert/readback and bounded candidate-search calls use typed Gmail
  methods only; no send/forward/delete/label mutation operation is available.
- Discovery computes a fixed UTC six-calendar-month boundary, persists H0 and
  the operation-backed epoch before provider discovery, admits a recent message
  and enqueues complete non-draft thread expansion/message work including older
  history, and does not advance a partition when durable writes fail.
- Normal History consumes every page/token, persists typed `messagesAdded` and
  action-label events plus resolve jobs before final cursor commit, and replay
  deduplicates event/action/job effects.  A 404 is reported as bounded attention
  state and is not treated as an empty poll.
- Fault/restart tests cover H0, page persistence, cursor ordering and duplicate
  label changes.  Synthetic body/header/attachment/provider-error sentinels do
  not reach DB, logs, stdout/stderr or temporary files.

## Risks and stop gates

Stop if an operation requires bypassing the owner transaction/repositories,
adding a schema row or generic provider framework, importing the spike, storing
raw bytes outside memory, or treating History 404 as normal success.  Target
insert/projection and full recovery remain later units.

## Verification

Run focused adapter/discovery/history tests, then locked Ruff/format/pytest,
`facet` and `facet-spike` help, repository safety, and wheel smoke.  Record the
exact base/head and leave live Gmail/deployment evidence explicitly pending.
