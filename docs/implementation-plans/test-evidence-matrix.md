# P1-02 test-foundation evidence

Date: 2026-10-02. Delivery: provider/helpers plus mandatory core compatibility candidate.
Owner: P1-02 delegated worker. Tracking: [Issue #5](https://github.com/GhostFlying/facet/issues/5).
Provider/helper starting base: `09031e723af1ef6590dc6746744ee52894501e38`.
Current CT implementation base: `b1e4ae08f7e361518eaa4f7fb1ae9f7f0b278f28`.
Approved [plan](p1-02-test-foundations.md) first-53808-byte prefix SHA-256:
`000e7c079108edceaa50b902d421e06b2e99cf333dd4b86d3f36bab5827512e9`.
Inputs: integrated `p1-core-v1` / `p1-writer-v1` at 09031 and reviewed actual
M1-01 types merged in PR #11 at b1e; root verified main CI 36980646059 and
dispatched CT implementation after that gate. No feature-specific
provider/SQL/wire/public-DTO extension is implemented by this unit.

Candidate commit, independent review and exact-head CI are recorded in the focused
PR and Issue, not a self-referential document commit. Local verification below is
complete for this working candidate; independent candidate acceptance is pending.
CT-01 through CT-04 are implemented and locally passed against actual merged
types. P1-02 awaits this new candidate's independent review, exact-head CI and
integration; do not close Issue #5 or release M1-02 until root verifies those
gates. No production milestone follows from test-foundation completion.

## Actual local verification

Initial Python 3.13.5 lacked `_sqlite3`; SQLite tests failed collection. No test
was skipped or weakened. The coordinator authorized task-local runtime preparation
and retrieval of already locked wheels, without system/dependency/lock changes.
Using uv 0.12.2's built-in managed-Python catalog, installed CPython 3.12.13 with:

```text
uv python install 3.12.13 --install-dir <task-runtime> --no-bin --no-registry --no-config --no-cache
uv sync --locked --extra dev --python <task-runtime>/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12 --no-python-downloads
```

The task runtime is in the coordinator-approved owner-only sibling tool directory,
outside this repository; no executable/default/system registration was changed.
Its source is uv's default managed CPython distribution (no custom mirror/catalog).
Observed Python 3.12.13, SQLite 3.53.1; `_sqlite3` import and an in-memory `SELECT 1`
passed. The first locked offline sync found a missing CPython 3.12 wheel; authorized
locked retrieval succeeded, and all subsequent checks were offline. This runtime
probe is not M1-02 production WAL/filesystem/deployment acceptance.

| Command | Actual result |
| --- | --- |
| `uv run --frozen --offline --no-python-downloads ruff check .` | PASS |
| `uv run --frozen --offline --no-python-downloads ruff format --check .` | PASS |
| `uv run --frozen --offline --no-python-downloads pytest tests/unit/test_fakes_gmail.py tests/unit/test_fakes_faults.py tests/unit/test_fakes_privacy.py -q` | PASS, 126 tests after the metadata-format review correction |
| `uv run --frozen --offline --no-python-downloads pytest tests/unit/test_fakes_contract_compatibility.py -q` | PASS, 92 CT parameterized tests |
| `uv run --frozen --offline --no-python-downloads pytest -q` | PASS, 379 tests, including merged M1-01 and unchanged Phase 0/repository tests |
| `uv run --frozen --offline --no-python-downloads facet --help` | PASS, package entrypoint only, not complete CLI/G1 acceptance |
| `uv run --frozen --offline --no-python-downloads facet-spike --help` | PASS, no service/auth startup |
| Original approved plan SHA-256 comparison | PASS, first 53808 bytes remain byte-identical; append-only execution handoff added |
| `git diff --check` and explicit new-file inspection | PASS; staged repository safety is additionally required before commit/push |

Counts include parameterized hook/marker/core cases, not separate production
invariants, performance measurements or live Gmail evidence. The provider-only
150-test baseline is historical; b1e adds M1-01 tests, this slice adds 92 CT cases.

### Independent review correction: get metadata format

The first candidate `a26fce7c30f39e4533bc10b16a8f0f8ec6d969c5` received
changes-requested: metadata could retain a seeded full MIME payload and thread
metadata ignored header selection. This was a genuine fake-semantic defect, not
a failing production test. The correction makes both get interfaces emit only
selected top-level headers for metadata, excluding body/parts/raw/snippet, and
applies the same boundary to explicitly scripted get responses. Full payloads
and raw message bytes retain their separate behavior.

The additional 12 parameterized controls in
`test_metadata_is_headers_only_with_filter_and_copy_isolation` and
`test_scripted_get_cannot_bypass_metadata_projection` cover both APIs, nested
content exclusion, absent/empty/mixed-case/nonmatching header selections,
preserved duplicate header order/casing, deep-copy isolation, full-format retention
and minimal-format payload absence. These remain synthetic wire-shape controls,
not actual Gmail verification. Revised c18 passed independent review and
candidate/main CI and actually merged in PR #10. Its approval does not approve
this subsequent CT candidate; the first candidate's 138-test result is historical.

Primary definitions rechecked on 2026-10-02:
[Gmail message formats](https://developers.google.com/workspace/gmail/api/reference/rest/v1/Format),
[message get header selection](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get),
[thread get formats/header selection](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get).

## Helper cases versus future feature consumers

All 21 TF rows have a passing helper control. Their future production-consumer
column remains `feature_consumer_pending`; a hook self-test or exception is not
proof of real commit/crash/lock/receipt behavior. Short test names below refer to
the three files in `tests/unit/test_fakes_*.py`, without duplicating runtime policy.

| Case / contract | Helper status and exact control | Future feature consumer and forbidden conclusion |
| --- | --- | --- |
| TF-01 / CC-01 | `helper_verified`: `test_history_pages_replay_overlap_and_final_cursor`, `test_legacy_and_remove_readd_events_are_observations_only` | M1-02/M4-01/M5-01: real durable event/action/message/repair keys; fake does not dedupe or admit |
| TF-02 / CC-07 | `helper_verified`: `test_later_page_failure_empty_poll_and_wrong_tokens`; `test_every_declared_hook_can_interrupt_independently` for event/cursor/fence/scan hooks | M3-02/M4-01/02: H0/H1 durable-before-scan and final-page checkpoint; scripted historyId is not a committed cursor |
| TF-03 / CC-08 | `helper_verified`: `test_unknown_outcomes_observably_indistinguishable` covers effect and no-effect response loss; `test_insert_effect_boundaries_are_distinct` | M2-04: unknown certainty/recovery rather than blind retry; controller truth is not application provenance |
| TF-04 / CC-08 | `helper_verified`: `test_nonidempotent_insert_and_indefinitely_delayed_search` | M2-04: no exactly-once/zero-search proof; fake never imposes a maximum indexing delay |
| TF-05 / CC-08 | `helper_verified`: `test_unmanaged_and_duplicate_rfc_ids_are_only_provider_facts`, `test_fake_refuses_scripted_nonprovider_oracles` | M2-04: no automatic binding/adoption/deletion of old or other-writer copies; fingerprint/attribution algorithms remain absent |
| TF-06 / CC-01/08 | `helper_verified`: unmanaged/reused-ID test, `test_source_loss_after_listing_and_missing_rfc_id`, MIME missing-ID case | M2-02/04: source identity, content match and normal visibility remain independent; no matching algorithm is tested here |
| TF-07 | `helper_verified`: `test_http_failure_uses_official_error_shape_without_classifying` for 400/401/403/429/500/503 and Retry-After; unknown transport test | M2-01/04: real error classification/retained work/no unconditional insert retry; HttpError is only synthetic input |
| TF-08 / CC-06 | `helper_verified`: `test_every_declared_hook_can_interrupt_independently`, `test_transport_overlap_fails_but_independent_worker_proceeds`, effect-boundary test | M2-03/M5-03: actor-serialized stop/dispatch both orderings and in-flight result retention; no fake generation state machine |
| TF-09 | `helper_verified`: source-loss tests before get and after unknown insert; `test_message_and_thread_formats_and_copy_isolation` rejects thread raw | M2-03/04: source_missing/refetch/recovery without disk raw; target existence is not permission to reinsert |
| TF-10 / CC-02/03/11 | `helper_verified`: every-hook tests for journal/submit/accept/effect/response/lookup; `test_close_releases_barriers_even_on_failure` | M1-03/M6-02: real stable-key receipt/authoritative lookup/restore-lineage tests; no receipt or wire model invented |
| TF-11 / CC-04/14 | `helper_verified`: overlap test and `test_transaction_probe_at_fake_network_boundary` using an actual SQLite connection | M1-03/M2-03: real process-owner locks, credential serialization and production network transaction prohibition |
| TF-12 / CC-07/10 | `helper_verified`: `test_early_interruption_does_not_consume_later_provider_script`, bounded fault consumption tests | M1-02/M4-01/M6-02: disk/fsync/process-death durability and no-empty-DB recovery; exceptions alone do not prove it |
| TF-13 | `helper_verified`: `test_estimates_and_list_pagination_are_scripted_not_truth`, empty poll and delayed-search tests | M1-05/M4-04: genuine totals/unique success/freshness/units/unknown metrics; no Dashboard DTO exists here |
| TF-14 / CC-12 | `helper_verified`: `test_sqlite_logical_and_active_wal_leaks_before_checkpoint`, `test_active_rollback_journal_marker_is_detected`, explicit files/log/console tests | M1-02/M2/M6: apply sentinels to real production sinks, including failure paths; marker-only violation controls are not raw mail fixtures |
| TF-15 / CC-12 | `helper_verified`: `test_legitimate_metadata_is_not_falsely_rejected`, `test_same_metadata_rejected_from_public_and_logs` | M1-05/M4-04/05: real allowlist serializers and browser DOM/network/export; buffers are not a pretend public model |
| TF-16 / CLI-08 | `helper_verified`: credential exception, content-everywhere, captured stdout/stderr/log and provider-error trace tests | All command owners: actual CLI subprocess output/privacy; private CLI cannot print content/tokens/provider errors |
| TF-17 / CC-09/10 | `helper_verified`: every-hook credential/maintenance/backup/bundle labels, barrier cleanup and timeout tests | M1-04/M6-01/02: real cache revisions, owner/view/credential lock ordering, coherent backup/restore |
| TF-18 | `helper_verified`: unknown/unconsumed script tests; network lower-layer probe, requests/httplib2, explicit Unix allowance, child-local guard | P1-02 guard itself verified; future child/browser tests require their own exact isolation, not inherited parent monkeypatches |
| TF-19 | `helper_verified`: `test_synthetic_mime_in_memory_only`, `test_raw_and_headers_stay_out_of_call_and_fault_evidence`, fixture raw-budget/release test | M2-02/03: semantic fidelity/thread/date/raw-byte production budget; fake does not parse/reserialize inserted raw or verify Gmail fidelity |
| TF-20 | `helper_verified`: `test_labels_legacy_facts_and_guarded_cleanup`, remove/re-add event test | M5-01/02/03: legacy no-execution, durable action dedupe and convenience cleanup retries; fake has no rules |
| TF-21 | `helper_verified`: `test_profile_wire_has_no_scope_or_binding_oracle` | M1-04/06: actual scopes/role/profile binding verification separately; profile has exactly Gmail fields |

## Mandatory core compatibility: locally verified against actual merged types

| Case | Status | Actual control and remaining acceptance |
| --- | --- | --- |
| CT-01 | `core_compatibility_verified` locally; candidate gates pending | `test_ct01_*`: exact 47 exports/modules, all 27 enum value sets, six unions/four direct records, exact required fields/tags and missing/drifted export negative controls |
| CT-02 | `core_compatibility_verified` locally; candidate gates pending | `test_ct02_*`: actual primitive bounds/UTC/integer units, required-nullables, provider-shaped non-contiguous History strings, event identity/enrichment, positive generation and every partition/progress guard |
| CT-03 | `core_compatibility_verified` locally; candidate gates pending | `test_ct03_actual_metadata_two_privacy_layers`: explicit actual RuleRef/SourceEvent/JobSubject/Claim fields; internal metadata passes, same IDs fail public, content/credential/output markers fail both layers; no DTO/SQL invented |
| CT-04 | `core_compatibility_verified` locally; candidate gates pending | `test_ct04_fault_callbacks_hold_real_selectors_without_transition_or_trace_leaks`: real recovery/read/claim/guard and independent axes retained across two bounded helper exceptions; safe traces and leak negative control |

Cases reside in `tests/unit/test_fakes_contract_compatibility.py`, without skips,
fallback imports, duplicate types or guessed JobKey/Binding/DTO/provider models.
Review binds this candidate to actual b1e inputs and p1-core-v1, not only a plan.
Independent review/CI/integration remain externally recorded release gates.
Helpers do not prove durable SQL dedupe, receipt replay or production recovery.

## Scope limits and safe reuse

- Across P1-02, only `tests/fakes/`, root conftest, four helper/core test files
  and two owned planning/evidence documents changed. This CT slice touches only
  its new test file and those documents. Production/spike sources,
  existing tests, dependencies, CI and shared status files are unchanged.
- The fake supports a deliberately small Google-style service/request surface.
  Unknown methods/arguments and unexpected page scripts fail. Unscripted search
  supports only empty query or exact `rfc822msgid:<...>`; broader queries require
  explicit pages. It never runs Gmail's general search language or discovery.
- Returned dictionaries are provider observations, not a new production provider
  result protocol. Unknown non-provider oracle fields are refused. Controller
  state remains Python test setup, not a security sandbox against introspection.
- A separate transport per worker probes overlaps. Call/hook traces contain only
  fixed method/hook names, ordinals, test transport IDs, monotonic times, controlled
  outcomes and sizes. They never copy raw, provider bodies, message IDs or scopes.
- The network guard patches explicit Python socket/DNS/send/client connection
  paths and is verified against a replaced lower layer before real I/O. It is not
  an OS sandbox against native extensions or malicious bypass. A subprocess test
  explicitly installs its own guard; no inheritance claim. Local Unix access is
  denied by default and allowed only within an explicitly scoped context.
- SQLite/file inspections accept only explicitly supplied test-owned sinks, bound
  inspected bytes/rows/files, reject symlink escapes, and permit credential markers
  only at exact owner-only credential files. Content remains forbidden there.
  Encoding probes are regression controls, not a proof against every covert store.
- No real Gmail/OAuth/private spike state, send/delete/purge API, deployment,
  image publication, release or external contact was used. Synthetic raw exists
  only in process memory; disk tests contain marker-only metadata violations.
