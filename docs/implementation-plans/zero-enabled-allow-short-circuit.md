# Rule-driven initial discovery and zero-enabled-allow short-circuit (Rev13)

## Scope and decision

Normal initial discovery must not enumerate the entire source mailbox. Build a
bounded Gmail `messages.list` candidate query from the enabled
`ALLOW_SENDER` and `ALLOW_DOMAIN` members pinned to the sealed epoch ruleset,
combined with the existing fixed date window and `includeSpamTrash=false`.
Gmail matching is only a provider-side candidate superset: local strict
metadata validation remains authoritative for normalized sender equality,
domain/subdomain dot boundaries, effective time, account, draft, and
Spam/Trash state. Use one deterministic OR query and the existing one
source-window page token; deterministic message-ID deduplication occurs before
metadata reads. Query construction is a bounded adapter input, not a generic
provider-query framework. If the rules exceed the adapter's bounded query
representation, fail closed with a typed maintenance/input result rather than
falling back to an unfiltered mailbox scan. Sort/deduplicate normalized terms;
sender terms use quoted `from:` values with quote/backslash escaping, domain
terms use broad `from:` canonical-domain tokens without unsupported wildcards;
OR/braces combines the union. Bound the rendered query to 4096 UTF-8 bytes
(including the fixed window); overflow is typed `invalid_input`, never an
unfiltered fallback. This is a Facet bound, not a claimed Gmail limit.

Primary references document `from:` and OR/braces but do not prove arbitrary
domain/subdomain candidate completeness: [Gmail API filtering](https://developers.google.com/workspace/gmail/api/guides/filtering)
and [Gmail search operators](https://support.google.com/mail/answer/7190).
Synthetic tests must not be represented as Gmail evidence. Before enabling the
domain-query branch for real use, require an independently accepted bounded
provider evidence fixture for parent domain, nested subdomains, and deceptive
suffixes. Until that separate gate passes, domain discovery returns a typed
maintenance hold, not zero matches/completion or a full scan. No new live test
authority is inferred from this implementation plan.

When the sealed ruleset has no enabled `ALLOW_SENDER` or `ALLOW_DOMAIN` member
(blacklist-only and disabled allow rules included), no source mailbox list or
candidate metadata request is useful or authorized for that initial epoch. The
producer records zero admitted threads/jobs through the existing writer path
and completes the pinned rule-selected admission scope: partition `COMPLETE`,
epoch `CATCHING_UP`, `discovery_complete=true`, `known_message_total=0` only for
the zero-allow selected scope. These values do not claim the mailbox was
inspected or is empty. The existing H0 History catch-up advances the epoch to
`DRAINING`, preserving live action-label authorization rather than leaving a
perpetual catching-up state. Progress/runbook wording must explicitly describe
rule-selected work, not all mailbox messages. The marker is idempotent.

Existing legacy initial epochs may have unfiltered progress/page tokens. For
an epoch whose pinned sealed snapshot has zero enabled allow members, the
single writer may complete that selected empty scope without using its token:
retain factual old page/observed counts, H0, IDs, jobs, and checkpoint lineage;
clear only the partition page token through existing guarded COMPLETE
transition, then advance the epoch and normal catch-up. Require nonterminal
initial/source-window lineage and no uncertain discovery/attention condition;
hold inconsistent cases. For nonempty snapshots with existing progress, old
unfiltered tokens must NOT be reused with a new query. Hold
`maintenance_required` for a separately reviewed query-lineage transition,
never reset/delete rows or silently restart a different query. Newly prepared,
zero-page partitions can start the pinned query directly.

History polling still starts from the existing fenced H0/cursor and continues;
action-label observation, tracked threads, existing jobs, insert recovery, and
typed provider/list errors are unchanged. A later enabled allow rule is
prospective: future History/action events use current rules and may discover
eligible threads, while this pinned initial epoch is not retroactively scanned.
Explicit future backfill/start commands retain existing request/ruleset guards;
this unit does not add automatic historical expansion.

## Files and tests

- `src/facet/gmail/source.py`: accept a typed, bounded discovery-query input
  generated for the epoch; preserve fixed window, Spam/Trash exclusion, one
  page-token flow, `MESSAGE_LIST` failures, and candidate metadata stages.
- `src/facet/projection/admission.py`, `src/facet/sync.py`, and
  `src/facet/runtime/foreground_runtime.py`: expose only a
  closed predicate/query input for enabled allow rules; generate deterministic
  sender/domain candidate terms without exposing rule values; keep local strict
  admission authoritative after provider results. Resolve the epoch's pinned
  sealed snapshot, not current rules, for initial discovery; current rules
  remain the future-event policy. Recheck snapshot identity at publication.
- `src/facet/projection/backfill.py`: use the query-driven source path; when
  the sealed snapshot has no enabled allow, persist the idempotent zero-admission
  marker above without list/candidate calls, including guarded legacy no-allow
  progress. Do not alter jobs, H0, History,
  action-label, or target-write paths.
- `tests/unit/test_m2_adapter_history.py` and source-query tests: assert exact
  synthetic sender/domain query construction, fixed window/Spam exclusion,
  pagination/deduplication, local boundary filtering, bounded-query refusal,
  and typed list failures; domain provider-evidence gate is distinct from
  these synthetic assertions.
- `tests/unit/test_sync.py`/backfill tests: no-enabled-allow performs zero
  provider list or candidate metadata calls, records no jobs, and replays the
  same partition/epoch state without revision drift.
- `tests/integration/test_foreground_runtime.py` and
  `tests/cli/test_bootstrap.py`: H0/checkpoint and History/action-label polling
  still run; a later rule plus a future fake History message admits only that
  event; no retroactive initial scan occurs; no-rule scope completes then
  reaches DRAINING after real fake History catch-up. Cover legacy 47-page
  no-allow progress and nonempty old-token maintenance hold.
- `docs/gmail-projection-spec.md`/`docs/oauth-setup.md` (concise existing
  progress wording only): clarify selected-scope completion is not a mailbox
  inventory or a claim that unchecked mail is valid/empty.
- No schema/migration, OAuth scope, raw storage, concurrency, timeout, retry,
  public DTO, target-write, deployment, or generic provider-framework changes.

## Acceptance and stop gates

1. With enabled allow rules, discovery requests only the deterministic Gmail
   candidate query (never an unfiltered window), paginates with the existing
   source-window token, deduplicates IDs, and still performs local strict
   metadata/admission checks before any job is admitted.
2. With no enabled allow, there are zero `messages.list` and candidate
   metadata calls, zero admissions/jobs, an idempotent partition marker, and
   selected-scope completion/known work zero; no empty-mailbox or
   metadata-verification claim is emitted. H0 catch-up reaches live DRAINING.
3. List/provider failures on rule-driven queries remain typed and do not
   advance the affected page; H0, epoch fencing, History cursors,
   action-label events, tracked threads, jobs, and unknown-insert recovery stay
   durable.
4. Restart does not repeat completed no-op work or alter revisions. Adding an
   allow rule later affects only future History/action events and explicit
   backfill requests, never an implicit historical disclosure expansion.
5. Existing admission, backfill, History, CLI privacy, full offline pytest,
   Ruff/format, and repository-safety gates pass with synthetic data only.

Stop before implementing/using a query branch if Gmail query semantics cannot
provide a bounded candidate superset without weakening local exact matching;
domain-specific uncertainty remains a typed hold until its evidence gate.
Stop if multiple query cursors or old-token resume require a schema migration,
if existing epoch/dashboard invariants reject selected-scope completion, or if provider/list errors, rule effective
times, privacy, or recovery semantics would be suppressed. No live Gmail,
OAuth, real state volume, deployment, image publication, or proxy/config
changes are part of this unit.
