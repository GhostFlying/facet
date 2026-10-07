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
