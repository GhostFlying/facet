# Consume duplicate per-message label events once

2026-10-08. Base main `f5f39c849cbd9342c83ec7555955e0624ce979d1`.
Root implements; independent Sol xhigh reviews plan and candidate.

## Observed product defect

Gmail reports a thread label activation on multiple messages. The contract
deduplicates business commands by projection/history record/label/thread, not
message. The current consumer instead rejects a different event ID after finding
the already executed canonical action. Real testing learned two sender rules but
created three false `resolve_event/request_conflict` attention jobs. Read-only
joins confirmed identical activation keys, executed canonical commands and
different message/event IDs. Independent synthetic file-backed reproduction
confirmed one rule/action/expansion with an incorrectly rejected alias event.

## Minimal implementation and acceptance

- `projection/action_consumer.py`: recognize an added-label alias only after its
  exact canonical activation is fully executed. Reuse registration/dedup identity;
  never change the canonical command's event ID or rerun business work.
- `db/repositories/events.py`: narrowly allow zero-effect alias consumption only
  after checking projection/history-record/label/thread, executed canonical action,
  consumed canonical event/completed canonical resolve job and owned alias claim.
  Atomically consume the alias event and complete its resolve job. No source read,
  rule publication, thread admission/reactivation, expansion, insert or stop change.
- Focused repository/consumer integration tests: multiple-message AddSender,
  AddDomain and BlackList, replay/restart, alias after stop, incomplete canonical,
  mismatched key, no sender fetch/business duplication, rollback and privacy.
- Keep old attention/unknown untouched. Normal queued-event repair is not a
  general attention override. Existing failed rows require separate explicit live
  repair authority and a reviewed bounded operation; no direct SQL shortcut.

Affected tests during iteration; final prescribed offline checks/CI and independent
candidate review remain required. Qualify a local non-root image with production
CLI external-only fake Gmail label events before another real copying cycle.
Keep the already submitted real cycle running safely to completion; preserve its
blocked receipt, verify aggregate state and diagnose mappings read-only. Do not
resubmit it or waive its attention stop gate.

## Explicitly authorized repair addendum

The user now explicitly authorizes completing the three newly failed real alias
records and the code fix/merge. Add one narrow repository repair operation reusing
the canonical completion proof. Require both alias event and resolve job to be
`needs_attention/request_conflict`, explicit event/job revision guards, and no
remaining claim. Complete only this alias event/job pair, clearing those errors;
do not override any other attention reason, perform business effects or use Gmail.
Already completed exact aliases are inspectable/idempotent, not re-executed.
Normal sync never calls this repair operation or enumerates old attention.

Use the installed qualified image and held `StateOwner` for a bounded private
operator operation, not direct SQL. Freeze exactly the three new event/job IDs and
row digests by comparing the failed-cycle snapshot against its prior attention
baseline and requiring the proven activation-key join. Save a stable submitted
repair receipt before calling the production repository, no blind replay. Backup
the exact validated observed state first, even though its cycle receipt is blocked;
that backup is not permission to copy or a fabricated clean-cycle receipt.
After repair, check exactly three event/job completions, old 58 attention/unknown,
rules/epochs/checkpoint/mappings/attempts/stops unchanged. Fault tests cover wrong
reason, wrong state/revision, incomplete proof, no Gmail/business effects,
rollback and idempotent completion. Independent affected review is required before
the actual repair. Then one normal bounded restart checks no duplicate inserts.

No new accounts, rules/window, OAuth scopes, historical scan, mailbox mutation,
cleanup, unknown retry, deployment or Release. The user separately authorized
configured AddSender/AddDomain testing, not automatic repair of its failed state.
