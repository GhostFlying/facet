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
The final frozen-candidate full baseline and exact PR CI remain pending. A finite
live source-only domain search probe stopped at an expired read-only access
snapshot (`source_auth_required`), with no target calls or writes. This does not
establish that interactive OAuth is required: normal writer-owned refresh is the
next check after the upgrade backup. No live domain recall is claimed.

No actual Gmail operation was performed by the reviewer. Product and external
boundaries are in the short plan; offline results do not imply live acceptance.

Official provider reference:
[Gmail API search/filtering](https://developers.google.com/workspace/gmail/api/guides/filtering)
supports bounded date and From search; API does not perform UI alias expansion or
thread-wide search. [Search operators](https://support.google.com/mail/answer/7190)
document From and OR. Neither is an exhaustive parent/subdomain recall SLA.
