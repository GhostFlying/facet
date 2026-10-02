# Phase 0 Gmail Projection Spike Results

**Experiment date:** 2026-10-01

**Review completed:** 2026-10-02

**Status:** Complete. Gmail API feasibility and target Gmail UI checks passed
within the sampled coverage. AI connector behavior belongs to the AI products
and is not a Facet release gate.

This document contains only redacted and aggregate findings. OAuth tokens,
account addresses, Gmail IDs, subjects, raw MIME, message bodies, and attachment
contents remain in the ignored private runtime directory.

## Executive result

The proposed Gmail-to-Gmail projection data plane is viable:

- raw Gmail messages can be inserted without sending them;
- original dates, RFC Message-IDs, MIME leaf payloads, inline images, and
  attachments survive the projection;
- a mixed incoming/sent conversation can be reconstructed as one target Gmail
  thread;
- source History includes both incoming messages and the source user's sent
  replies;
- a thread-level action label produces multiple message-level History events
  that can be safely aggregated by History record, label, and thread;
- target search by RFC Message-ID can recover an insert whose local completion
  record was deliberately lost.

The user subsequently confirmed the four-message target conversation is
visible and the representative three-PDF message and its attachments can be
opened in target Gmail. The new [project plan](project-plan.md),
[product contract](product-contract.md), and
[implementation specification](gmail-projection-spec.md) incorporate these
findings and the agreed product boundary.

These experiments establish feasibility, not production completeness. The
four-message sample includes source-sent messages with pre-existing `Fwd:`
subjects; the projection preserves them rather than creating forwarding mail.
Broader reply/thread edge cases, trusted authentication policy, durable workers,
History 404 recovery, and long-running deployment remain Phase 1 work.

On 2026-10-02 the user reported cleanup of source action labels and target mail.
A read-only follow-up confirmed the action labels were absent. At that snapshot,
the bound target API still returned eight ordinary messages and one draft; two
known spike samples remained present and unlabeled, and Spam/Trash also contained
mail. This is a setup observation, not a new copy operation. The evidence remains
historical, and production setup must establish a fresh checkpoint and mappings
without assuming that Inbox cleanup emptied All Mail.

The spike also disproved two stronger assumptions:

- target raw bytes are not byte-identical to source raw bytes because Gmail adds
  a target-side `Received` header;
- Gmail does not deduplicate repeated `messages.insert` calls by RFC Message-ID.

## Evidence

| Experiment | Result | Evidence |
| --- | --- | --- |
| OAuth account isolation | Pass | Source and target profiles resolved to distinct accounts and were bound to their roles. |
| Source read scope | Pass | `gmail.readonly` supported profile, search, raw message, thread, label, and History reads. |
| Target write/read scopes | Pass | `gmail.insert` inserted messages and `gmail.readonly` supported post-insert verification and reconciliation. |
| Four-message conversation | Pass | Two external messages and two source-sent messages with pre-existing forwarding subjects became one target thread with no fallback. |
| Date fidelity | Pass | RFC Date and Gmail `internalDate` matched source for every copied sample. |
| MIME payload fidelity | Pass | All leaf MIME part content hashes matched after target readback. |
| Attachment fidelity | Pass | A representative message containing text, HTML, inline images, and three PDF attachments retained all 18 MIME leaf parts and their payload hashes. |
| Raw byte identity | Expected fail | Target raw differed because Gmail added one `Received` header; stable headers and MIME payloads matched. |
| Crash-window recovery | Pass | After insert succeeded and the process exited before recording the response, `rfc822msgid` found exactly one target candidate on the first check, 11.8 seconds after the pending record was created. |
| Repeated insert deduplication | Fail | Repeating the same raw insert produced two target messages in two distinct target threads with the same internal date. |
| Incoming History | Pass | The controlled test thread produced one matching incoming `messagesAdded` event. |
| Sent-reply History | Pass | The source user's reply produced a second matching `messagesAdded` event on the same thread. |
| Thread action label | Pass | Applying `AI/AddDomain` once produced two `labelsAdded` events in one History record, one per current message, with the same thread ID. |
| Legacy action labels | Isolated | Pre-existing labeled mail did not affect the result because the experiment used a cursor captured before the controlled actions and filtered by label ID, test subject, and thread ID. |
| Sender authentication sample | Pass with limited sample | Representative Hyatt messages exposed SPF, DKIM, and DMARC pass results. Broader provider samples are still required before defining a global admission policy. |
| Target mailbox visibility | Pass | Inserted messages had no target labels and were confirmed visible in All Mail. They are not placed in Inbox or a dedicated projection label by default. |
| Target UI and PDF access | Pass | The user confirmed the four-message conversation and opened the representative PDF attachments. |
| AI connector retrieval | Outside Facet acceptance | Indexing, retrieval, and attachment handling are the responsibility of each AI product. Optional compatibility reports do not block Facet. |

## Required production-spec changes

### 1. State the delivery guarantee precisely

The projection is at-least-once with best-effort duplicate suppression. It is
not exactly-once across SQLite and Gmail.

For stale pending jobs:

1. do not immediately repeat the insert;
2. wait for a short search-index grace period;
3. search target by RFC Message-ID;
4. bind exactly one candidate after checking content and existing mappings;
5. quarantine zero or multiple candidates for retry or operator review;
6. only repeat insert after the not-found policy is satisfied.

Periodic reconciliation can detect duplicates. With target
`gmail.insert + gmail.readonly`, it cannot delete them automatically.

### 2. Do not use whole-raw SHA equality as target fidelity

Store source raw SHA-256 for source-side integrity, but do not expect target raw
SHA-256 to match. Target Gmail can add transport headers.

Use a projection fingerprint composed from stable headers and decoded MIME leaf
payload digests when a content comparison is required. RFC Message-ID remains
the primary recovery search key when present.

### 3. Serialize work within each source thread

The first insert establishes the target thread ID. Later messages must be
inserted oldest first and use that target ID. Concurrency is safe across
different source threads, not within one thread.

### 4. Aggregate label commands at thread level

A single Gmail UI operation on a two-message thread generated two
message-level `labelsAdded` entries in one History record. Action handling must
deduplicate by an equivalent of:

```text
(history_record_id, action_label_id, source_thread_id)
```

The durable command must be recorded before an optional convenience-mode worker
removes the action label.

### 5. Make target visibility explicit

`messages.insert` without label IDs left all tested messages unlabeled. They are
available through All Mail, but not through Inbox or a dedicated sidebar view.

Phase 1 defaults to All Mail. A pre-existing `Facet/Projected` label can be
attached on insert when configured. Automatic label creation is optional and
requires the relevant label-management scope. Adding `INBOX` is an explicit
setting. No connector-facing test is required to choose this default.

### 6. Keep safe and convenience source modes

The readonly spike observed user-applied action labels successfully. Therefore
the default safe mode can support learning commands without source mutation,
provided action labels are created and cleared manually.

Convenience mode may request `gmail.modify` to create, clear, and add status
labels automatically.

### 7. Require sender-authentication policy work

The representative provider samples had SPF, DKIM, and DMARC pass results, but
the rule engine must not admit mail based only on a spoofable `From` header.
Exact registrable-domain rules and trusted Gmail authentication results should
be designed and tested together. Substring domain rules remain prohibited.

### 8. Preserve initialization fencing

Capture and persist a source History cursor before discovery, then consume from
that cursor while or after the initial backfill. This prevents messages arriving
during discovery from falling between the backfill and incremental phases.

## Phase 0 completion and next work

The target Gmail visibility and attachment manual checks are complete. The user
explicitly placed AI connector behavior outside Facet's responsibility, so there
are no remaining Phase 0 manual gates.

Phase 1 readiness is governed by the durable sync, admission, recovery, and
deployment acceptance criteria in the project plan. An optional third-party
compatibility matrix may be maintained later, without making connector indexing
or retrieval part of Facet's delivery guarantee.
