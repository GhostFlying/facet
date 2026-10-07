# Gmail insert request compatibility

Base: `8c534ee`. Bounded corrective unit; no product or schema change.

## Cause and scope

The production TargetAdapter passes `neverMarkSpam` to `messages.insert`.
The locked Google client discovery rejects that keyword before any HTTP call.
Synthetic resources accepting arbitrary kwargs hid the incompatibility. The
worker conservatively persisted unknown outcomes, so existing live jobs remain
blocked/recovery rather than being silently reset.

- Remove the unsupported keyword from `src/facet/gmail/target.py`.
- Update two exact synthetic request expectations in
  `tests/unit/test_projection_worker.py`.
- Add `tests/unit/test_gmail_target_discovery.py`, using the real locked
  Google discovery/client with only HTTP responses substituted. Cover both
  Date policies, optional thread anchor, unchanged raw bytes, zero automatic
  retries and one request per insert. No real credentials or network.
- Record concise current product evidence in `docs/development-status.md`.

## Acceptance and boundaries

The new test must fail on the old adapter before transport and pass after the
fix; focused adapter/worker/CLI tests, Ruff and safety must pass. Run full offline
tests at the final candidate boundary. Rebuild the unchanged Dockerfile on
sgbox and test the candidate image locally. Independent implementation review
checks the actual commit. Do not change insert to import/send, expand scopes,
add headers, reset cursor, alter generation, or mutate old attempts/jobs.

Live recovery execution of already-blocked jobs is a separate authorization
boundary; a missing target search result does not authorize retry. Keep the
real daemon stopped until its network path and recovery prerequisites are
resolved. Container IPv6 overrides used for diagnosis are not a general
deployment-network guarantee.
