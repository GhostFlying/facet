# Rule-match timeline layout

2026-10-10. Base: `46898a6775c632d3a553d1827ec4a659c42348a0`.
Root implements; independent reviewer checks the final candidate.

## Delivery and scope

- `src/facet/web/static/index.html`: show activity times to whole seconds,
  keep each activity on one line, use separate kind/rule/count/time columns,
  and contain horizontal scrolling inside the activity panel on narrow screens.
  Do not round or change stored timestamps or API sorting. Keep complete rule
  text accessible, do not lose counts/timestamps or add mail details.
- `tests/browser/dashboard.cjs`: verify desktop/mobile single-line geometry,
  second precision, long rule text and no viewport overflow. Keep existing
  fresh/stale, bounded GET-only and privacy cases.
- No visual run separators are added: activity rows are intentionally a
  time-ordered stream because the current snapshot does not persist exact cycle
  boundaries. Do not imply that time gaps are sync-cycle boundaries.
- `docs/dashboard-spec.md` and `docs/development-status.md`: concise handoff,
  evidence and any remaining separator limitation.

## Acceptance and boundaries

Focused HTTP/static checks and actual synthetic browser at 1440x900 / 390x844;
final required offline checks, independent review and exact-head CI before merge.
No Gmail calls, rule/credential/DB mutations or extra disclosure. Deployment is
not part of this initial layout implementation; preserve the qualified running
image until any authorized replacement is qualified.
