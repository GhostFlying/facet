# Gmail insert compatibility acceptance

Date: 2026-10-07. Implementation candidate:
`1b09b8f629d00e7ba7573e311ff6c764664d76fe`, base `8c534ee`.
Plan: [bounded correction](../implementation-plans/gmail-insert-discovery-compatibility.md).

Independent reviewer: `insert_compatibility_review`, `gpt-6.1-sol` high,
not the implementation author. Verdict: approved; no concrete findings.

The reviewer independently passed all seven real-discovery/HTTP-fake tests and
reproduced the former unsupported keyword's TypeError with zero HTTP calls.
The production change removes only `neverMarkSpam` from `messages.insert`.
Exact raw bytes, Date policy, thread anchor, zero automatic insert retries and
unknown-outcome recovery are retained. No send/import/delete operation, scope,
schema or existing live attempt/job mutation was introduced. Diff whitespace
checks passed. The written plan matches the bounded implementation.

Coordinator acceptance passed 90 focused tests, repository Ruff/format checks,
spike CLI help and repository safety. Four new cases failed on the old adapter
and passed after the correction. Full-suite results are recorded in the current
status after completion, not inferred from this review.

The unmodified pinned Dockerfile was built on sgbox via Tailscale SSH and
imported locally. Candidate image `facet:1b09b8f`, OCI revision equal to the
candidate above, user `10001:10001`, local amd64 image ID:
`sha256:09ac52e3886bea51a76dfefade35ac29e8ec8a49e51e84e04ce8d830650a0de3`.
This is a local image ID, not a published registry manifest digest. No arm64 or
GHCR publication evidence is claimed for this candidate.

Actual Google client request construction passed inside that image with
networking disabled. Separate Compose project `facet-insert-1b09b8f` completed
the production CLI path with synthetic Gmail/OAuth only: init, authorization
and binding, rule addition, preview, explicit start, run once, readback and
mapping. One mapping was confirmed; a second process projected zero messages
and retained the mapping. No state was inserted directly into the DB. The real
deployment volume and stopped service were not upgraded by these checks.

This evidence does not authorize live repair, another insert for an existing
unknown outcome, target cleanup or unmanaged-content adoption. The real target
prerequisite, container network path and incremental admission gap remain open.

## Shared-fake alignment follow-up

The same independent reviewer approved the narrow delta from `1b09b8f` to
`9d2d6ef1b799c10c864eab461cb27957538255e0`, with no findings; 66 shared-fake,
adapter/history and real-discovery tests passed independently. A missed older
adapter expectation had still required the invalid keyword. The delta corrects
that expectation, removes the keyword from the fake's allowed arguments and
tests rejection before request construction. Existing result and forbidden
send/delete assertions remain. The coordinator's 90-test focused set also
passed. Production source, lockfile, package inputs and Dockerfile are unchanged;
the prior production review and image/Compose evidence remain valid.

The earlier full run is not acceptance: it encountered the obsolete adapter
expectation and an operator SIGINT surfaced in a subprocess fixture. The
corrected candidate requires its own uninterrupted full-suite result, recorded
in current status. Neither failure was hidden or treated as a passing gate.

Final coordinator acceptance at `9d2d6ef`: the complete offline suite passed
2653 tests in 500.10 seconds. Locked environment sync, repository Ruff/format,
spike help and safety also passed. This receipt changes documentation only;
it does not modify tested production source or test behavior. CI, integration,
image publication, real-service upgrade and successful live projection are
not claimed.
