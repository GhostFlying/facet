# Existing-queue continuation receipt

2026-10-08. Root executes; independent Sol xhigh reviews the bounded operational
change. User authorizes draining the original accounts/rules/fixed window and
final checks, not a new scope or permanent service.

## Bound candidates

The [short operational plan](../implementation-plans/same-scope-queue-drain.md)
passed independent review at SHA256
`d843dd067623e4adce1b7af6a0c7aa7fa90108e68f14457f77660d751b2daba9`.
At the start of continuation, production source/image was the accepted
`1a8eef14937caf8f58bc8035eb964e3b7bcec38f`; source/tests/build inputs are identical
to base main `f5f39c849cbd9342c83ec7555955e0624ce979d1`. No production code,
schema, rules, configuration or scope changed.

Only the existing private operator's ordered `drain1`–`drain3` modes and exact-phase
sample selector changed. Independent acceptance approved operator SHA256
`a1ccb5111a71a4aa6a01d3a7f5404d29b1029380ac8a61739a86a7327c50af26`
and selector `df8d34da84f528b04bb24e938a911e65a211054d3a6e1868fc021a78e87a3783`.
Root/reviewer independently passed 72 entirely synthetic tests. A concrete
one-shot final-save failure finding was fixed: a blocked receipt cannot qualify
the next phase or sample even if completion/clean fields remain present.
Other valid review conclusions were retained; no source requalification was needed.

The user then authorized adding configured AddSender/AddDomain tags during the
copy pass, checking current-cycle isolation and next-cycle learning. The addendum
passed independent review at plan SHA256
`9583ca70f60f4c4d56b36ae1b88511cbd77c8a2b620173fed17c11931b2636a4`.
`drain1` retains its original guard; `drain2`/`drain3` narrowly accept enabled
action-label-origin sender/domain additions backed by newly executed corresponding
actions. Config/bindings/label mappings, original rules/actions, old unknowns,
mappings, stops and historical scope remain protected. The rule-only comparison
normalization never changes the stored actual snapshots. Independent acceptance
approved operator `dc529fa173909b5cb19918e70775f3a461b338903b865187ac4a208aaf9ab9ee`
and selector `e9f090652b44b66a71f5f9830fa98612080619246c37f80aa1fc59f8842e8569`;
root/reviewer independently passed 96 pure checks. A sample-count finding was
fixed: old action-selected mappings are sampled but never counted as phase-new.
Exact-phase new mappings and up to 20 action-selected threads use the same bounded
read-only fidelity checks, including a previously mapped selected thread.

## Execution evidence

Pre-continuation writer-locked SQLite-API/config/credential backup passed at
2873 mappings. Existing production manager-owned credential preparation verified
both role accounts/scopes; the full business snapshot remained exactly the prior
completed cycle's snapshot. Fresh target enumeration found 2873 mapped items,
two permitted source-identity outbound items and no other unmanaged mail.

`drain1` completed with 1000 new mappings, 3873 total, in 1856.18s. The current
copy pass did not consume the newly added action labels. Target classification
found 3873 mapped items, two permitted outbound items and no other unmanaged mail.
Twenty phase-new mappings passed read-only MIME/digest, valid Date/internalDate,
thread and normal All Mail checks.

`drain2` produced 427 verified mappings, 4300 total, and completed the original
historical epoch (5041 completed work items). The following History cycle executed
two AddSender actions, learning two enabled sender rules (three total); no live
AddDomain learning is claimed. All projection/expansion queues drained, claims
were zero and target classification found 4300 mapped items plus the same two
permitted outbound items, with no other unmanaged mail. Its acceptance guard
correctly blocked on three new `resolve_event/request_conflict` attention rows:
duplicate per-message notifications after successful canonical thread actions.
The failed receipt remains blocked, never resubmitted or relabelled clean.

The separately authorized [alias fix](action-label-event-aliases.md) has now
completed only these three event/job pairs, after a validated blocked-state
writer-locked backup. The network-disabled operation used the installed qualified
repository under `StateOwner`; it made no Gmail writes or business effects. Old
58 attention jobs, one unknown, 4300 mappings, attempts, rules, checkpoint, epoch
and stops were unchanged. Read-only diagnostic sampling of this exact failed
phase covered 22 new mappings, including both action-selected threads: MIME/
digests, all 22 valid dates/internalDate values, threads and normal All Mail
visibility passed. This sample is diagnostic evidence, not a clean-cycle receipt.

The separate production CLI restart completed in 29.51s and added six verified
new-source mappings, 4306 total, with no repeat insert, new problems or warnings.
Historical work stays completed; original scope, mappings, old unknown/attention,
stops and discovery identity were preserved. Fresh target enumeration found
4306 mapped items, two permitted outbound items and no other unmanaged mail.
Read-only fidelity checks of all six restart-added mappings passed MIME/digests,
valid dates/internalDate, threads and normal All Mail visibility. The final
writer-locked private backup passed at 4306 mappings, three sender rules, original
58 attention jobs and one old unknown; the business snapshot stayed unchanged.
Old unknown/attention/stopped work remains protected, not successful. No browser,
exhaustive-content, new deployment or complete Phase 1 acceptance is implied.
