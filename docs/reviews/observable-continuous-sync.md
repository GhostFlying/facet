# Observable continuous sync review

Base: `97c4093905aa94c8754054eefeeb5c2696143cf1`. Root implementation;
independent reviewer `continuous_plan_review`, Sol 6.1 xhigh.
Plan SHA-256 `6f8cdcd6daa5a7660671e85143674c8772826220462b5a8d54a63208617215ec`:
APPROVE. No mandatory plan correction. Reviewer confirmed the sole production
insert consumer, lazy pre-claim inventory outside SQLite transactions, shared
cycle cache, preserved History and ownership/outbound precedence. Pagination
must invoke progress/stop hooks, not merely phase exits. Bounded From-domain
search can ship with strict local admission; exhaustive arbitrary-domain recall
is not a new gate, concrete missed eligible live samples remain a stop condition.

Implementation/acceptance APPROVE for source candidate
`b0bce4d745c2a049064be323e7871456fa93b59d` against the same base and plan revision.
The independent reviewer ran 105 passing tests across target inventory, closed
logging, worker, sync, complete CLI and wire suites. Review confirmed callbacks
outside page/job transactions, resumable final History pages, graceful stop,
pre-claim fail-closed target inventory and preserved recovery ownership.

The candidate's packaged production source/static files match the local image
`facet:observable-continuous-b0bce4d`, image ID
`sha256:ea747cff0b00f4a4a57d5e321e6662195343ad0d5c7638df7544679b1059ab54`.
Ten selected complete CLI/domain/outbound/401-refresh/known-readback/automatic-
recovery scenarios passed inside this image as UID 10001, read-only root, ephemeral
private state and no network. Fake Gmail/OAuth substitutes only external calls;
production source is packaged, not overlaid. Continuous CLI acceptance observes
intermediate confirmed counts and a new History request after process restart,
then stops cleanly without duplicate insert.

An earlier development full run found 13 obsolete empty-stderr assertions now
updated to validate closed log JSON and privacy sentinels; affected suites pass.
The final frozen-source full baseline passed: 2944 tests in 831.04 seconds;
locked dependencies, Ruff/formatting, CLI smoke and repository safety passed.
Exact-head Python 3.12/3.13 and image PR CI passed at
`6b1f1565144ca6ecfea8362507235feae6152785`; the docs-only increment retained the
source review and received bounded accuracy/privacy review. PR
[#110](https://github.com/GhostFlying/facet/pull/110) merged at
`7fa0cc7a761e29628b4753729bf452d994f30e00`, with unchanged production/test/Compose
content relative to the approved source candidate.

No actual Gmail operation was performed by the reviewer. Product and external
boundaries are in the short plan; offline results do not imply live acceptance.

Official provider reference:
[Gmail API search/filtering](https://developers.google.com/workspace/gmail/api/guides/filtering)
supports bounded date and From search; API does not perform UI alias expansion or
thread-wide search. [Search operators](https://support.google.com/mail/answer/7190)
document From and OR. Neither is an exhaustive parent/subdomain recall SLA.

## Current test deployment and bounded live acceptance

The initial read-only query probe encountered an unusable access snapshot.
The separately reviewed private preflight (SHA-256
`0c2eede892eeb344ea677b3c6137f5dfd2a070cc5ef30d17b6830ca66564fbee`) acquired
StateOwner, backed up SQLite/config/credentials/journal, used ordinary production
credential refresh/profile checks and verified exact checked business-row/config
equality before a second backup. Both original profiles passed; no interactive
OAuth or mailbox write was needed. No operator business SQL correction occurred.

Three existing sender samples were compared with From-domain and parent queries
inside the selected fixed window: eight finite searches, no omitted IDs,
including two actual subdomain samples. No source raw reads, target calls/writes
or SQLite mutation from the probe. This does not prove universal Gmail recall.
Read-only pre-upgrade target enumeration found 4325 mapped, two allowed source-
From SENT items, zero other unmanaged and zero draft items.

Main publication succeeded. Anonymous import selected
`ghcr.io/ghostflying/facet:7fa0cc7a761e29628b4753729bf452d994f30e00`, index
`sha256:ce959c76121793d8b17691b436c9d139859813607267bc6edc1a9c8c8dc11498`.
The amd64 configuration/image ID is
`sha256:682bc1c02d5f79c5e97e1b49c01b55f1a75b44f9307dcf6fbdf85b0a98996f45`.
amd64/arm64 manifests, each SPDX 2.3 payload and SLSA-v1 subject/source revision
were checked by digest; all packaged source/static files match the qualified
checkout. This is not live arm64 host acceptance.

The original Compose project/volume was retained, UID 10001, read-only root,
loopback HTTP, restart unless stopped, 90-second stop grace and three rotated
10 MB logs. Ordinary `run` resumed only the already selected scope. The first
cycle completed in 73621 ms, adding 15 confirmed mappings (4325 to 4340); jobs
drained with zero attention or active unknown. Dashboard served fresh in-cycle
snapshots before final success, without public digests/mail metadata.

Graceful stop exited zero; stopped/locked post-write backups and owner profile
checks passed. A new process completed a zero-insert cycle in 9875 ms; 4340
mappings and 4342 total insert-attempt records remained unchanged, no claims or
attention. Production recovery list reports zero active unknown and one retained
assumed-absent historical record: state-only SQL counts must not mistake it for
active recovery. Final read-only target inventory found all 4340 mappings, two
permitted outbound and zero other unmanaged items. Continuous testing stays on.

No deletion, source write, send, new OAuth scope, arbitrary historical expansion,
production migration or Release. Remaining maintenance/restore/browser/production
dogfood acceptance is not completed. Persisted role verification timestamps are
not timestamps of every runtime profile request; cycle freshness is separate.
