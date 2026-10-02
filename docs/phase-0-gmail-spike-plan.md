# Phase 0 Gmail Projection Spike Plan

Phase 0 is complete as of 2026-10-02. See the
[results](phase-0-gmail-spike-results.md) and the
[Phase 1 project plan](project-plan.md). The acceptance boundary was updated by
the user: Facet ends at correct target Gmail materialization and readback;
third-party AI connector behavior is optional compatibility work.

## Objective

Validate the Gmail-specific assumptions that the Facet projection architecture
depends on before building the durable backfill and History daemon.

The spike is intentionally small. It is not the production projection service
and does not establish the final database schema.

## Questions to answer

1. Can a source message be copied with `messages.get(format=raw)` and
   `messages.insert(internalDateSource=dateHeader)` while preserving useful
   headers, MIME bodies, attachments, and dates?
2. Can a real mixed incoming/sent conversation be reconstructed as one target
   Gmail thread when messages are inserted oldest first?
3. After an insert succeeds but local state is not updated, how quickly can the
   target find the message with `rfc822msgid`, and what happens if the raw
   message is inserted again?
4. Where do inserted messages appear in Gmail, and are their conversation and
   attachments usable through the target Gmail UI?
5. Which History events are produced for incoming messages, source replies,
   and labels applied to a message or an entire thread?
6. Do real allowed-sender samples expose authentication results that can support
   a conservative admission policy without rejecting legitimate mail?
7. Can source and target OAuth credentials be acquired and refreshed safely in
   the intended headless deployment workflow?

## Implementation scope

- A Python 3.11+ CLI under `src/facet_spike`.
- Separate source and target token files.
- Source scope: `gmail.readonly`.
- Target scopes: `gmail.insert` and `gmail.readonly`.
- OAuth through Google's supported Desktop loopback flow.
- Commands to inspect profiles, copy one message, copy one thread, simulate the
  insert/record crash window, reconcile by RFC Message-ID, capture/poll Gmail
  History, and render a redacted evidence report.
- Session data stored under an ignored local directory with restrictive file
  permissions.
- Unit tests for local MIME/header parsing, evidence redaction, state handling,
  and deterministic request construction. Live Gmail behavior is recorded as
  integration evidence rather than mocked into a false success.

## Explicit non-goals

- Six-month discovery or backfill.
- Production SQLite schema and worker queues.
- Automatic rules, sender admission, or label mutation.
- Docker image and long-running daemon.
- Automatic deletion or duplicate repair.
- OAuth tokens or raw message bodies in logs or reports.

## Execution stages and gates

### Stage 1: Local harness

- Build the CLI and tests.
- Verify that secrets and runtime evidence are ignored by Git.
- Verify that reports omit raw bodies, token values, subjects, and addresses by
  default.

Gate: local tests pass and the CLI can explain the required OAuth setup.

### Stage 2: OAuth and account guardrails

- Authorize one source account and one distinct target account.
- Read both profiles and persist their expected account identities.
- Refuse to run copy operations if both roles resolve to the same account or if
  a token is later replaced by a different account.

Gate: both accounts are healthy, distinct, and refreshable.

### Stage 3: Raw message and thread experiments

- Copy a representative MIME message.
- Copy a real multi-message thread oldest first.
- Compare source and target metadata and raw hashes where Gmail permits it.

Gate: useful date, MIME, attachment, and conversation behavior is preserved.

### Stage 4: Crash/reconciliation experiment

- Persist a pending experiment record.
- Insert the target message.
- terminate before recording the target response.
- Search immediately and after controlled delays by RFC Message-ID.
- Optionally repeat the insert to observe duplicate behavior.

Gate: a defensible stale-pending recovery policy can be written from measured
search-index latency and duplicate behavior.

### Stage 5: History and target Gmail verification

- Capture a source History cursor.
- Perform incoming, reply, and label actions.
- Poll and record event shapes.
- Ask the user to verify target Gmail conversation visibility and PDF access.

Gate: History events cover required changes and target Gmail displays the
inserted content and attachments correctly.

## Stop conditions

Do not proceed to the production daemon if any of these remain unsupported:

- representative raw MIME content or attachments are corrupted;
- multi-message conversations cannot be reconstructed with acceptable fallback
  behavior;
- target Gmail cannot expose the inserted content and attachments correctly;
- OAuth cannot be operated safely in the intended self-hosted environment.

## Deliverables

- The runnable spike CLI and tests.
- A redacted machine-readable evidence log.
- A generated Markdown result report with pass, partial, fail, or untested for
  each architectural assumption.
- A short list of required changes to the production Gmail projection spec.
