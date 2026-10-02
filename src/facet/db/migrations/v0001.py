"""Trusted, fixed schema-v1 manifest, expanded from the approved closed catalogue.

All builders are private and consume only literals in this module. Neither
configuration nor rows can add SQL, columns, discriminators, indexes or triggers.
"""

from dataclasses import dataclass

from facet.contracts import enums as core

from .. import codecs

APPLICATION_ID = 0x46414354
VERSION = 1


@dataclass(frozen=True, slots=True)
class _Table:
    name: str
    columns: tuple[tuple[str, str, bool], ...]
    primary: tuple[str, ...]
    unique: tuple[tuple[str, ...], ...]
    checks: tuple[str, ...]


_ENUMS = {
    cls.__name__: tuple(item.value for item in cls)
    for module in (core, codecs)
    for cls in vars(module).values()
    if isinstance(cls, type)
    and issubclass(cls, core.StrEnum)
    and cls.__module__ == module.__name__
}


def _columns(spec: str) -> tuple[tuple[str, str, bool], ...]:
    result = []
    for field in spec.split():
        name, kind = field.split(":")
        result.append((name, kind.removesuffix("?"), kind.endswith("?")))
    return tuple(result)


def _table(name, spec, primary, unique=(), checks=()):
    return _Table(name, _columns(spec), tuple(primary.split()), unique, checks)


def _null_pair(a, b):
    return f"(({a} IS NULL AND {b} IS NULL) OR ({a} IS NOT NULL AND {b} IS NOT NULL))"


def _branch(tag, variants, fields):
    branches = []
    for discriminator, required in variants.items():
        predicates = [f"{tag}='{discriminator}'"]
        predicates.extend(
            f"{column} IS {'NOT ' if column in required else ''}NULL"
            for column in fields
        )
        branches.append("(" + " AND ".join(predicates) + ")")
    return "(" + " OR ".join(branches) + ")"


_ADMISSION = (
    "tag:AdmissionOrigin epoch_id:L? rule_id:L? rule_revision:R? "
    "policy_version:K? preview_id:L? action_command_id:L?"
)
_ADMISSION_CHECK = _branch(
    "tag",
    {
        "initial_backfill": ("epoch_id", "rule_id", "rule_revision", "policy_version"),
        "future_rule": ("rule_id", "rule_revision", "policy_version"),
        "manual_thread": ("preview_id",),
        "action_label": ("action_command_id",),
    },
    (
        "epoch_id",
        "rule_id",
        "rule_revision",
        "policy_version",
        "preview_id",
        "action_command_id",
    ),
)
_DECISION = "tag:Decision operation_id:L? preview_id:L? ruleset_revision:R?"
_DECISIONS = {
    "backfill_start": ("operation_id", "preview_id", "ruleset_revision"),
    "gap_approval": ("operation_id", "preview_id", "ruleset_revision"),
    "scheduled_reconcile": ("ruleset_revision",),
    "requested_reconcile": ("operation_id", "ruleset_revision"),
    "scheduled_target_audit": (),
    "requested_target_audit": ("operation_id",),
}
_ENUMS["Decision"] = tuple(_DECISIONS)
_DECISION_CHECK = _branch(
    "tag", _DECISIONS, ("operation_id", "preview_id", "ruleset_revision")
)
_ENUMS["Partition"] = (
    "source_window",
    "source_thread",
    "target_catalog",
    "mapped_target_set",
)
_ENUMS["EventTag"] = ("message_added", "message_deleted", "label_changed")
_PARTITION_CHECK = _branch(
    "tag",
    {
        "source_window": (),
        "source_thread": ("source_thread_id",),
        "target_catalog": (),
        "mapped_target_set": (),
    },
    ("source_thread_id",),
)
_EVENT_CHECK = _branch(
    "tag",
    {
        "message_added": (),
        "message_deleted": (),
        "label_changed": ("label_id", "change"),
    },
    ("label_id", "change"),
)

_SUBJECT_FIELDS = (
    "source_message_id",
    "source_thread_id",
    "generation",
    "repair_operation_id",
    "event_id",
    "operation_id",
    "read_kind",
    "attempt_id",
    "subject_epoch_id",
    "partition_epoch_id",
    "partition_key",
    "action_command_id",
)
_SUBJECTS = {
    "project_message": ("source_message_id", "source_thread_id", "generation"),
    "repair_message": (
        "source_message_id",
        "source_thread_id",
        "generation",
        "repair_operation_id",
    ),
    "expand_thread": ("source_thread_id", "subject_epoch_id", "generation"),
    "resolve_event": ("event_id",),
    "operation_read": ("operation_id", "read_kind"),
    "recover_insert": ("attempt_id",),
    "scan_discovery": ("subject_epoch_id", "partition_epoch_id", "partition_key"),
    "scan_gap": ("subject_epoch_id", "partition_epoch_id", "partition_key"),
    "reconcile_source": ("subject_epoch_id", "partition_epoch_id", "partition_key"),
    "audit_target": ("subject_epoch_id", "partition_epoch_id", "partition_key"),
    "cleanup_action": ("action_command_id",),
}

_VERIFICATION = (
    _null_pair("verified_address", "verified_at"),
    "state<>'verified' OR (verified_address IS NOT NULL AND verified_at IS NOT NULL)",
)
_TARGET_PAIR = _null_pair("target_message_id", "target_thread_id")
_SEMANTIC_PAIR = _null_pair("semantic_digest", "semantic_version")
_ATTEMPT_AXES = (
    "("
    + " OR ".join(
        (
            "(state='prepared' AND certainty='not_attempted' AND dispatch_started_at "
            "IS NULL AND result_at IS NULL AND verified_at IS NULL AND "
            "target_message_id IS NULL AND attribution='none')",
            "(state='cancelled_before_dispatch' AND certainty='not_attempted' AND "
            "dispatch_started_at IS NULL AND result_at IS NOT NULL AND verified_at IS "
            "NULL AND target_message_id IS NULL AND attribution='none')",
            "(state='dispatch_started' AND certainty='unknown' AND dispatch_started_at "
            "IS NOT NULL AND result_at IS NULL AND verified_at IS NULL AND "
            "target_message_id IS NULL AND attribution='none')",
            "(state='definite_not_inserted' AND certainty='definitely_not_inserted' "
            "AND result_at IS NOT NULL AND verified_at IS NULL AND target_message_id "
            "IS NULL AND attribution='none')",
            "(state='pending_recovery' AND certainty='unknown' AND dispatch_started_at "
            "IS NOT NULL AND result_at IS NOT NULL AND verified_at IS NULL AND "
            "target_message_id IS NULL AND attribution='none')",
            "(state='known_inserted' AND certainty='inserted' AND dispatch_started_at "
            "IS NOT NULL AND result_at IS NOT NULL AND verified_at IS NULL AND "
            "target_message_id IS NOT NULL AND attribution='direct_response')",
            "(state='verified' AND certainty='inserted' AND dispatch_started_at IS NOT "
            "NULL AND result_at IS NOT NULL AND verified_at IS NOT NULL AND "
            "target_message_id IS NOT NULL AND semantic_digest IS NOT NULL AND "
            "attribution='direct_response')",
            "(state='needs_attention' AND dispatch_started_at IS NOT NULL AND "
            "result_at IS NOT NULL AND verified_at IS NULL AND ((certainty='unknown' "
            "AND target_message_id IS NULL AND attribution='none') OR "
            "(certainty='inserted' AND target_message_id IS NOT NULL AND "
            "attribution='direct_response')))",
        )
    )
    + ")"
)

TABLES = (
    _table(
        "schema_metadata",
        "singleton:N schema_version:SchemaVersion registry_digest:H created_at:T",
        "singleton",
        checks=("singleton=1",),
    ),
    _table(
        "schema_migrations",
        "version:SchemaVersion name:MigrationName checksum:H applied_at:T",
        "version",
        (("name",),),
    ),
    _table(
        "projections",
        "projection_id:P singleton:N state_instance_id:L request_namespace:L "
        "config_revision:R ruleset_revision:R source_mode:SourceMode "
        "binding_state:BindingState restore_state:RestoreState daemon_paused:B "
        "last_owner_run_id:L? created_at:T",
        "projection_id",
        (("singleton",), ("state_instance_id",), ("request_namespace",)),
        ("singleton=1",),
    ),
    _table(
        "bindings",
        "projection_id:P role:Role declared_address:PrivateAddress "
        "verified_address:PrivateAddress? credential_revision:R binding_revision:R "
        "state:BindingState verified_at:T?",
        "projection_id role",
        checks=_VERIFICATION,
    ),
    _table(
        "binding_revisions",
        "projection_id:P role:Role binding_revision:R declared_address:PrivateAddress "
        "verified_address:PrivateAddress? state:BindingState verified_at:T?",
        "projection_id role binding_revision",
        checks=_VERIFICATION,
    ),
    _table(
        "rules",
        "projection_id:P rule_id:L kind:RuleKind normalized_value:RuleValue "
        "current_revision:R",
        "projection_id rule_id",
        (("projection_id", "kind", "normalized_value"),),
    ),
    _table(
        "rule_revisions",
        "projection_id:P rule_id:L revision:R enabled:B effective_at:T "
        "origin:RuleOrigin policy_version:K",
        "projection_id rule_id revision",
    ),
    _table(
        "rulesets",
        "projection_id:P revision:R created_at:T sealed:B",
        "projection_id revision",
    ),
    _table(
        "ruleset_members",
        "projection_id:P ruleset_revision:R rule_id:L rule_revision:R",
        "projection_id ruleset_revision rule_id",
    ),
    _table(
        "tracked_threads",
        "projection_id:P source_thread_id:V active:B generation:G admitted_at:T "
        "stopped_at:T? stop_reason:ThreadStopReason? admission_revision:R",
        "projection_id source_thread_id",
        checks=(
            "generation>=1",
            "(active=1 AND stopped_at IS NULL AND stop_reason IS NULL) OR (active=0 "
            "AND stopped_at IS NOT NULL AND stop_reason IS NOT NULL)",
        ),
    ),
    _table(
        "thread_admissions",
        "projection_id:P source_thread_id:V admission_revision:R generation:G "
        "admitted_at:T " + _ADMISSION,
        "projection_id source_thread_id admission_revision",
        checks=("generation>=1", _ADMISSION_CHECK),
    ),
    _table(
        "epochs",
        "projection_id:P epoch_id:L kind:EpochKind state:EpochState revision:R "
        "created_at:T window_start:T? window_end:T? discovery_cutoff:T? "
        + _DECISION
        + " gap_id:L? recovery_margin_us:N? fence_history_id:V? "
        "fence_recorded_at:T? catchup_history_id:V? discovery_complete:B "
        "known_message_total:N?",
        "projection_id epoch_id",
        checks=(
            _DECISION_CHECK,
            _null_pair("window_start", "window_end"),
            "window_start IS NULL OR window_start<window_end",
            _null_pair("fence_history_id", "fence_recorded_at"),
            "(kind='history_gap' AND gap_id IS NOT NULL AND tag "
            "IN('scheduled_reconcile','gap_approval')) OR (kind<>'history_gap' AND "
            "gap_id IS NULL AND recovery_margin_us IS NULL)",
            "(kind IN('initial_backfill','historical_expansion') AND "
            "tag='backfill_start' AND window_start IS NOT NULL AND discovery_cutoff IS "
            "NOT NULL) OR (kind='source_reconcile' AND tag "
            "IN('scheduled_reconcile','requested_reconcile')) OR (kind='target_audit' "
            "AND tag IN('scheduled_target_audit','requested_target_audit') AND "
            "window_start IS NULL AND discovery_cutoff IS NULL) OR (kind='history_gap' "
            "AND window_start IS NOT NULL)",
            "recovery_margin_us IS NULL OR recovery_margin_us=300000000",
        ),
    ),
    _table(
        "history_gaps",
        "projection_id:P gap_id:L failed_poll_id:L failed_cursor:V "
        "checkpoint_cursor:V? checkpoint_revision:R observed_at:T "
        "reliable_coverage_at:T? h1:V h1_recorded_at:T",
        "projection_id gap_id",
        checks=(_null_pair("checkpoint_cursor", "reliable_coverage_at"),),
    ),
    _table(
        "epoch_partitions",
        "projection_id:P epoch_id:L partition_key:KeyBytes tag:Partition "
        "source_thread_id:V? state:PartitionState completed_pages:N observed_items:N "
        "page_token:ProviderPageToken? after_source_message_id:V? revision:R",
        "projection_id epoch_id partition_key",
        checks=(
            _PARTITION_CHECK,
            "page_token IS NULL OR tag IN('source_window','target_catalog')",
            "after_source_message_id IS NULL OR tag='mapped_target_set'",
            "state<>'not_started' OR (completed_pages=0 AND observed_items=0 AND "
            "page_token IS NULL AND after_source_message_id IS NULL)",
            "state<>'complete' OR page_token IS NULL",
        ),
    ),
    _table(
        "source_events",
        "projection_id:P event_id:L event_key:KeyBytes tag:EventTag "
        "history_record_id:V source_message_id:V label_id:V? change:LabelChange? "
        "observed_at:T source_thread_id:V? processing:EventProcessing revision:R "
        "error_code:ErrorCode?",
        "projection_id event_id",
        (("projection_id", "event_key"),),
        (
            _EVENT_CHECK,
            "error_code IS NULL OR processing IN('needs_attention','source_missing')",
        ),
    ),
    _table(
        "history_checkpoints",
        "projection_id:P cursor:V? reliable_coverage_at:T? revision:R "
        "active_poll_id:L?",
        "projection_id",
        checks=(_null_pair("cursor", "reliable_coverage_at"),),
    ),
    _table(
        "history_polls",
        "projection_id:P poll_id:L origin:PollOrigin origin_epoch_id:L? start_cursor:V "
        "start_checkpoint_revision:R started_at:T state:PollState completed_pages:N "
        "next_page_token:ProviderPageToken? final_history_id:V? finished_at:T? "
        "revision:R",
        "projection_id poll_id",
        checks=(
            "(origin='checkpoint' AND origin_epoch_id IS NULL) OR "
            "(origin<>'checkpoint' AND origin_epoch_id IS NOT NULL)",
            "(state='reading' AND finished_at IS NULL AND final_history_id IS NULL) OR "
            "(state='completed' AND finished_at IS NOT NULL AND final_history_id IS "
            "NOT NULL AND next_page_token IS NULL) OR (state='abandoned' AND "
            "finished_at IS NOT NULL AND final_history_id IS NULL)",
        ),
    ),
    _table(
        "history_pages",
        "projection_id:P poll_id:L ordinal:N response_history_id:V "
        "input_page_token:ProviderPageToken? next_page_token:ProviderPageToken? "
        "received_at:T metadata_digest:H expected_event_count:N complete:B",
        "projection_id poll_id ordinal",
        checks=("ordinal>=1", "ordinal<>1 OR input_page_token IS NULL"),
    ),
    _table(
        "history_page_events",
        "projection_id:P poll_id:L ordinal:N event_id:L",
        "projection_id poll_id ordinal event_id",
    ),
    _table(
        "sync_jobs",
        "projection_id:P job_id:L kind:JobKind key_version:N stable_key:KeyBytes "
        "priority:Priority state:JobState revision:R created_at:T updated_at:T "
        "next_attempt_at:T? attempt_count:N last_error_code:ErrorCode? "
        "origin_epoch_id:L? source_message_id:V? source_thread_id:V? generation:G? "
        "repair_operation_id:L? event_id:L? operation_id:L? read_kind:ReadTaskKind? "
        "attempt_id:L? subject_epoch_id:L? partition_epoch_id:L? "
        "partition_key:KeyBytes? action_command_id:L?",
        "projection_id job_id",
        (("projection_id", "key_version", "stable_key"),),
        (
            "key_version=1",
            _branch("kind", _SUBJECTS, _SUBJECT_FIELDS),
            "generation IS NULL OR generation>=1",
            "partition_epoch_id IS NULL OR partition_epoch_id=subject_epoch_id",
        ),
    ),
    _table(
        "epoch_jobs",
        "projection_id:P epoch_id:L job_id:L",
        "projection_id epoch_id job_id",
    ),
    _table(
        "job_claims",
        "projection_id:P job_id:L claim_id:L owner_run_id:L acquired_at:T "
        "thread_generation:G? job_revision:R phase:ClaimPhase",
        "projection_id job_id",
        (("projection_id", "claim_id"),),
        ("thread_generation IS NULL OR thread_generation>=1",),
    ),
    _table(
        "insert_attempts",
        "projection_id:P attempt_id:L job_id:L claim_id:L source_message_id:V "
        "source_thread_id:V generation:G binding_role:Role binding_revision:R "
        "prepared_at:T dispatch_started_at:T? result_at:T? "
        "requested_target_thread_id:V? raw_digest:H semantic_digest:H? "
        "semantic_version:K? rfc_message_id:RfcMessageId? date_policy:DatePolicy "
        "state:InsertState certainty:OutcomeCertainty target_message_id:V? "
        "target_thread_id:V? attribution:AttributionKind visibility:Visibility "
        "verified_at:T? error_code:ErrorCode? recovery_checks:N next_recovery_at:T? "
        "revision:R",
        "projection_id attempt_id",
        checks=(
            "binding_role='target'",
            "generation>=1",
            _TARGET_PAIR,
            _SEMANTIC_PAIR,
            _ATTEMPT_AXES,
        ),
    ),
    _table(
        "message_mappings",
        "projection_id:P source_message_id:V source_thread_id:V mapping_revision:R "
        "attempt_id:L target_message_id:V target_thread_id:V verified_at:T "
        "visibility:Visibility last_audit_at:T? target_present:B?",
        "projection_id source_message_id",
        (("projection_id", "target_message_id"),),
        (_null_pair("last_audit_at", "target_present"), "mapping_revision>=1"),
    ),
    _table(
        "mapping_history",
        "projection_id:P source_message_id:V mapping_revision:R source_thread_id:V "
        "attempt_id:L target_message_id:V target_thread_id:V verified_at:T "
        "superseded_at:T?",
        "projection_id source_message_id mapping_revision",
        checks=("mapping_revision>=1",),
    ),
    _table(
        "target_ownership",
        "projection_id:P target_message_id:V source_message_id:V first_attempt_id:L "
        "recorded_at:T",
        "projection_id target_message_id",
    ),
    _table(
        "thread_targets",
        "projection_id:P source_thread_id:V target_thread_id:V anchor:B "
        "first_attempt_id:L created_at:T",
        "projection_id source_thread_id target_thread_id",
    ),
    _table(
        "action_commands",
        "projection_id:P action_command_id:L event_id:L history_record_id:V label_id:V "
        "source_thread_id:V kind:ActionKind state:ActionState cleanup:CleanupState "
        "observed_at:T executed_at:T? error_code:ErrorCode? revision:R",
        "projection_id action_command_id",
        (("projection_id", "history_record_id", "label_id", "source_thread_id"),),
        (
            "(state='executed' AND executed_at IS NOT NULL) OR (state<>'executed' AND "
            "executed_at IS NULL)",
            "cleanup='not_requested' OR state='executed'",
        ),
    ),
    _table(
        "error_events",
        "projection_id:P error_id:L code:ErrorCode error_class:ErrorClass role:Role? "
        "observed_at:T job_id:L? attempt_id:L? count:N",
        "projection_id error_id",
        checks=("count>=1",),
    ),
    _table(
        "audit_events",
        "projection_id:P audit_id:L kind:AuditKind object_kind:AuditObjectKind "
        "local_object_id:L? source_thread_id:V? source_message_id:V? "
        "before_revision:R? after_revision:R? before_state:AuditState? "
        "after_state:AuditState? error_code:ErrorCode? observed_at:T",
        "projection_id audit_id",
    ),
    _table(
        "thread_expansion_runs",
        "projection_id:P run_id:L job_id:L source_thread_id:V epoch_id:L generation:G "
        "current:B state:PartitionState snapshot_digest:H expected_messages:N "
        "started_at:T completed_at:T? revision:R",
        "projection_id run_id",
        checks=(
            "generation>=1",
            "state IN('scanning','complete','needs_attention')",
            "(state='complete' AND completed_at IS NOT NULL) OR (state<>'complete' AND "
            "completed_at IS NULL)",
        ),
    ),
    _table(
        "thread_expansion_items",
        "projection_id:P run_id:L source_message_id:V kind:ExpansionItemKind "
        "project_job_id:L? mapped_source_message_id:V? mapping_revision:R?",
        "projection_id run_id source_message_id",
        checks=(
            _branch(
                "kind",
                {
                    "project_job": ("project_job_id",),
                    "verified_mapping": (
                        "mapped_source_message_id",
                        "mapping_revision",
                    ),
                },
                ("project_job_id", "mapped_source_message_id", "mapping_revision"),
            ),
            "mapped_source_message_id IS NULL OR "
            "mapped_source_message_id=source_message_id",
        ),
    ),
)

_AUDIT_PAIRS = {
    "initialized": "projection",
    "rule_changed": "rule",
    "thread_admitted": "thread",
    "thread_stopped": "thread",
    "epoch_started": "epoch",
    "page_ingested": "projection",
    "cursor_advanced": "projection",
    "job_state_changed": "job",
    "attempt_state_changed": "attempt",
    "mapping_verified": "mapping",
    "binding_changed": "projection",
    "restore_fenced": "projection",
    "maintenance_completed": "projection",
}
_AUDIT_SELECTORS = _branch(
    "object_kind",
    {
        "projection": (),
        "rule": ("local_object_id",),
        "thread": ("source_thread_id",),
        "epoch": ("local_object_id",),
        "event": ("local_object_id",),
        "job": ("local_object_id",),
        "attempt": ("local_object_id",),
        "mapping": ("source_message_id",),
    },
    ("local_object_id", "source_thread_id", "source_message_id"),
)
_ENUMS["AuditState"] = tuple(
    dict.fromkeys(
        v
        for cls in (core.BindingState, core.EpochState, core.JobState, core.InsertState)
        for v in (e.value for e in cls)
    )
)


def _literal(values):
    return "(" + ",".join("'" + value + "'" for value in values) + ")"


def _scalar(name, kind):
    if kind in {"N", "G", "R"}:
        return "INTEGER", f"{name} BETWEEN 0 AND 9223372036854775807"
    if kind == "T":
        return "INTEGER", f"{name} BETWEEN -62135596800000000 AND 253402300799999999"
    if kind == "B":
        return "INTEGER", f"{name} IN(0,1)"
    if kind == "SchemaVersion":
        return "INTEGER", f"{name} BETWEEN 1 AND 2147483647"
    if kind == "KeyBytes":
        return "BLOB", f"length({name}) BETWEEN 1 AND 8192"
    if kind in {"L", "H"}:
        n = 32 if kind == "L" else 64
        check = (
            f"length(CAST({name} AS BLOB))={n} AND instr({name},char(0))=0 "
            f"AND {name} NOT GLOB '*[^0-9a-f]*'"
        )
        if kind == "L":
            check += (
                f" AND substr({name},13,1)='4'"
                f" AND substr({name},17,1) IN('8','9','a','b')"
            )
        return "TEXT", check
    if kind == "P":
        return (
            "TEXT",
            f"length(CAST({name} AS BLOB)) BETWEEN 1 AND 64 "
            f"AND instr({name},char(0))=0 "
            f"AND {name} NOT GLOB '*[^A-Za-z0-9_-]*'",
        )
    if kind == "K":
        return (
            "TEXT",
            f"length(CAST({name} AS BLOB)) BETWEEN 1 AND 64 "
            f"AND instr({name},char(0))=0 "
            f"AND substr({name},1,1) GLOB '[a-z0-9]' "
            f"AND {name} NOT GLOB '*[^a-z0-9_.-]*'",
        )
    if kind == "MigrationName":
        return "TEXT", (
            f"length(CAST({name} AS BLOB))=5 AND instr({name},char(0))=0 "
            f"AND {name} GLOB 'v[0-9][0-9][0-9][0-9]'"
        )
    if kind == "ProviderPageToken":
        return (
            "TEXT",
            f"length(CAST({name} AS BLOB)) BETWEEN 1 AND 16384 "
            f"AND instr({name},char(0))=0",
        )
    if kind in {"V", "PrivateAddress", "RuleValue", "RfcMessageId"}:
        limit = {
            "V": 512,
            "PrivateAddress": 320,
            "RuleValue": 512,
            "RfcMessageId": 998,
        }[kind]
        checks = [f"length(CAST({name} AS BLOB)) BETWEEN 1 AND {limit}"]
        checks.extend(
            f"instr({name},char({n}))=0" for n in (*range(32), *range(127, 160))
        )
        return "TEXT", " AND ".join(checks)
    return "TEXT", f"{name} IN {_literal(_ENUMS[kind])}"


# Each suffix relation implicitly prepends projection_id. Only the four stated
# pointer cycles are deferred; all other references are immediate RESTRICT.
_FKS = {
    "projections": (("ruleset_revision", "rulesets", "revision", True),),
    "bindings": (
        ("role binding_revision", "binding_revisions", "role binding_revision", True),
    ),
    "rules": (
        ("rule_id current_revision", "rule_revisions", "rule_id revision", True),
    ),
    "rule_revisions": (("rule_id", "rules", "rule_id", False),),
    "ruleset_members": (
        ("ruleset_revision", "rulesets", "revision", False),
        ("rule_id rule_revision", "rule_revisions", "rule_id revision", False),
    ),
    "tracked_threads": (
        (
            "source_thread_id admission_revision",
            "thread_admissions",
            "source_thread_id admission_revision",
            True,
        ),
    ),
    "thread_admissions": (
        ("source_thread_id", "tracked_threads", "source_thread_id", False),
        ("epoch_id", "epochs", "epoch_id", False),
        ("rule_id rule_revision", "rule_revisions", "rule_id revision", False),
        ("action_command_id", "action_commands", "action_command_id", False),
    ),
    "epochs": (
        ("gap_id", "history_gaps", "gap_id", False),
        ("ruleset_revision", "rulesets", "revision", False),
    ),
    "history_gaps": (("failed_poll_id", "history_polls", "poll_id", False),),
    "history_polls": (("origin_epoch_id", "epochs", "epoch_id", False),),
    "epoch_partitions": (("epoch_id", "epochs", "epoch_id", False),),
    "history_checkpoints": (("active_poll_id", "history_polls", "poll_id", False),),
    "history_pages": (("poll_id", "history_polls", "poll_id", False),),
    "history_page_events": (
        ("poll_id ordinal", "history_pages", "poll_id ordinal", False),
        ("event_id", "source_events", "event_id", False),
    ),
    "sync_jobs": (
        ("origin_epoch_id", "epochs", "epoch_id", False),
        ("subject_epoch_id", "epochs", "epoch_id", False),
        (
            "partition_epoch_id partition_key",
            "epoch_partitions",
            "epoch_id partition_key",
            False,
        ),
        ("source_thread_id", "tracked_threads", "source_thread_id", False),
        ("event_id", "source_events", "event_id", False),
        ("attempt_id", "insert_attempts", "attempt_id", False),
        ("action_command_id", "action_commands", "action_command_id", False),
    ),
    "thread_expansion_runs": (
        ("job_id", "sync_jobs", "job_id", False),
        ("source_thread_id", "tracked_threads", "source_thread_id", False),
        ("epoch_id", "epochs", "epoch_id", False),
    ),
    "thread_expansion_items": (
        ("run_id", "thread_expansion_runs", "run_id", False),
        ("project_job_id", "sync_jobs", "job_id", False),
        (
            "mapped_source_message_id mapping_revision",
            "mapping_history",
            "source_message_id mapping_revision",
            False,
        ),
    ),
    "epoch_jobs": (
        ("epoch_id", "epochs", "epoch_id", False),
        ("job_id", "sync_jobs", "job_id", False),
    ),
    "job_claims": (("job_id", "sync_jobs", "job_id", False),),
    "insert_attempts": (
        ("job_id", "sync_jobs", "job_id", False),
        ("source_thread_id", "tracked_threads", "source_thread_id", False),
        (
            "binding_role binding_revision",
            "binding_revisions",
            "role binding_revision",
            False,
        ),
    ),
    "message_mappings": (
        ("attempt_id", "insert_attempts", "attempt_id", False),
        ("source_thread_id", "tracked_threads", "source_thread_id", False),
        (
            "source_message_id mapping_revision",
            "mapping_history",
            "source_message_id mapping_revision",
            False,
        ),
    ),
    "mapping_history": (
        ("attempt_id", "insert_attempts", "attempt_id", False),
        ("source_thread_id", "tracked_threads", "source_thread_id", False),
    ),
    "target_ownership": (("first_attempt_id", "insert_attempts", "attempt_id", False),),
    "thread_targets": (
        ("source_thread_id", "tracked_threads", "source_thread_id", False),
        ("first_attempt_id", "insert_attempts", "attempt_id", False),
    ),
    "action_commands": (("event_id", "source_events", "event_id", False),),
    "error_events": (
        ("job_id", "sync_jobs", "job_id", False),
        ("attempt_id", "insert_attempts", "attempt_id", False),
    ),
}


def _create(table):
    parts = []
    for name, kind, nullable in table.columns:
        sqltype, predicate = _scalar(name, kind)
        if nullable:
            predicate = f"{name} IS NULL OR ({predicate})"
        parts.append(
            f"{name} {sqltype}{'' if nullable else ' NOT NULL'} CHECK({predicate})"
        )
    parts.append("PRIMARY KEY(" + ",".join(table.primary) + ")")
    parts.extend("UNIQUE(" + ",".join(columns) + ")" for columns in table.unique)
    parts.extend("CHECK(" + predicate + ")" for predicate in table.checks)
    if table.name == "audit_events":
        parts.append("CHECK(" + _AUDIT_SELECTORS + ")")
        parts.append(
            "CHECK("
            + " OR ".join(
                f"(kind='{kind}' AND object_kind='{object}')"
                for kind, object in _AUDIT_PAIRS.items()
            )
            + ")"
        )
        for column in ("before_state", "after_state"):
            choices = []
            for object, cls in (
                ("projection", core.BindingState),
                ("epoch", core.EpochState),
                ("job", core.JobState),
                ("attempt", core.InsertState),
            ):
                choices.append(
                    f"(object_kind='{object}' AND {column} IN "
                    f"{_literal(tuple(v.value for v in cls))})"
                )
            parts.append(f"CHECK({column} IS NULL OR (" + " OR ".join(choices) + "))")
    relations = _relations(table)
    for child, parent, reference, deferred in relations:
        suffix = " DEFERRABLE INITIALLY DEFERRED" if deferred else ""
        parts.append(
            f"FOREIGN KEY({','.join(child)}) REFERENCES "
            f"{parent}({','.join(reference)}) ON DELETE RESTRICT "
            f"ON UPDATE RESTRICT{suffix}"
        )
    return f"CREATE TABLE {table.name}(" + ",".join(parts) + ") STRICT"


def _relations(table):
    result = []
    if table.name not in {"schema_metadata", "schema_migrations", "projections"}:
        result.append((("projection_id",), "projections", ("projection_id",), False))
    result.extend(
        (
            ("projection_id", *child.split()),
            parent,
            ("projection_id", *reference.split()),
            deferred,
        )
        for child, parent, reference, deferred in _FKS.get(table.name, ())
    )
    return tuple(result)


_UNRESOLVED = (
    "state IN('dispatch_started','pending_recovery','known_inserted','needs_attention')"
)
_INDEXES = (
    (
        "events_plain_identity",
        "source_events",
        "projection_id tag history_record_id source_message_id",
        True,
        "tag IN('message_added','message_deleted')",
    ),
    (
        "events_label_identity",
        "source_events",
        "projection_id history_record_id source_message_id label_id change",
        True,
        "tag='label_changed'",
    ),
    (
        "events_pending",
        "source_events",
        "projection_id processing observed_at event_id",
        False,
        None,
    ),
    (
        "partitions_simple_identity",
        "epoch_partitions",
        "projection_id epoch_id tag",
        True,
        "tag<>'source_thread'",
    ),
    (
        "partitions_thread_identity",
        "epoch_partitions",
        "projection_id epoch_id source_thread_id",
        True,
        "tag='source_thread'",
    ),
    (
        "partitions_pending",
        "epoch_partitions",
        "projection_id epoch_id state partition_key",
        False,
        None,
    ),
    (
        "jobs_project_identity",
        "sync_jobs",
        "projection_id source_message_id generation",
        True,
        "kind='project_message'",
    ),
    (
        "jobs_repair_identity",
        "sync_jobs",
        "projection_id repair_operation_id source_message_id generation",
        True,
        "kind='repair_message'",
    ),
    (
        "jobs_expand_identity",
        "sync_jobs",
        "projection_id source_thread_id subject_epoch_id generation",
        True,
        "kind='expand_thread'",
    ),
    (
        "jobs_resolve_identity",
        "sync_jobs",
        "projection_id event_id",
        True,
        "kind='resolve_event'",
    ),
    (
        "jobs_read_identity",
        "sync_jobs",
        "projection_id operation_id",
        True,
        "kind='operation_read'",
    ),
    (
        "jobs_recover_identity",
        "sync_jobs",
        "projection_id attempt_id",
        True,
        "kind='recover_insert'",
    ),
    (
        "jobs_scan_identity",
        "sync_jobs",
        "projection_id kind subject_epoch_id partition_key",
        True,
        "kind IN('scan_discovery','scan_gap','reconcile_source','audit_target')",
    ),
    (
        "jobs_cleanup_identity",
        "sync_jobs",
        "projection_id action_command_id",
        True,
        "kind='cleanup_action'",
    ),
    (
        "jobs_eligible",
        "sync_jobs",
        "projection_id state next_attempt_at priority created_at job_id",
        False,
        None,
    ),
    (
        "jobs_thread_generation",
        "sync_jobs",
        "projection_id source_thread_id generation state job_id",
        False,
        None,
    ),
    (
        "attempts_message_unresolved",
        "insert_attempts",
        "projection_id source_message_id",
        True,
        _UNRESOLVED,
    ),
    (
        "attempts_thread_unresolved",
        "insert_attempts",
        "projection_id source_thread_id",
        True,
        _UNRESOLVED,
    ),
    (
        "attempts_message_prepared",
        "insert_attempts",
        "projection_id source_message_id",
        True,
        "state='prepared'",
    ),
    (
        "attempts_recovery_due",
        "insert_attempts",
        "projection_id state next_recovery_at attempt_id",
        False,
        None,
    ),
    (
        "expansion_current",
        "thread_expansion_runs",
        "projection_id job_id",
        True,
        "current=1",
    ),
    (
        "expansion_job_runs",
        "thread_expansion_runs",
        "projection_id job_id started_at run_id",
        False,
        None,
    ),
    ("jobs_inspection", "sync_jobs", "projection_id created_at job_id", False, None),
    (
        "attempts_inspection",
        "insert_attempts",
        "projection_id prepared_at attempt_id",
        False,
        None,
    ),
    (
        "events_inspection",
        "source_events",
        "projection_id observed_at event_id",
        False,
        None,
    ),
    (
        "mappings_audit",
        "message_mappings",
        "projection_id source_message_id",
        False,
        None,
    ),
    (
        "actions_pending",
        "action_commands",
        "projection_id state cleanup observed_at action_command_id",
        False,
        None,
    ),
    ("audit_recent", "audit_events", "projection_id observed_at audit_id", False, None),
    (
        "thread_target_anchor",
        "thread_targets",
        "projection_id source_thread_id",
        True,
        "anchor=1",
    ),
)


def _indexes():
    indexes = list(_INDEXES)
    for table in TABLES:
        covered = [table.primary, *table.unique]
        covered.extend(
            tuple(columns.split())
            for _, name, columns, _, where in indexes
            if name == table.name and where is None
        )
        for columns, _, _, _ in _relations(table):
            if any(key[: len(columns)] == columns for key in covered):
                continue
            name = "fk_" + table.name + "_" + "_".join(columns)
            indexes.append((name, table.name, " ".join(columns), False, None))
            covered.append(columns)
    return tuple(indexes)


INDEXES = _indexes()


def _trigger(name, table, event, when="1"):
    return (
        f"CREATE TRIGGER {name} BEFORE {event} ON {table} WHEN {when} "
        "BEGIN SELECT RAISE(ABORT,'consistency_failure'); END"
    )


_IMMUTABLE_ROWS = (
    "schema_migrations",
    "binding_revisions",
    "rule_revisions",
    "thread_admissions",
    "history_gaps",
    "history_page_events",
    "target_ownership",
    "audit_events",
    "error_events",
    "epoch_jobs",
    "thread_expansion_items",
)
_MUTABLE = {
    "schema_metadata": (),
    "projections": (
        "request_namespace",
        "config_revision",
        "ruleset_revision",
        "source_mode",
        "binding_state",
        "restore_state",
        "daemon_paused",
        "last_owner_run_id",
    ),
    "bindings": (
        "verified_address",
        "credential_revision",
        "binding_revision",
        "state",
        "verified_at",
    ),
    "rules": ("current_revision",),
    "rulesets": ("sealed",),
    "tracked_threads": (
        "active",
        "generation",
        "admitted_at",
        "stopped_at",
        "stop_reason",
        "admission_revision",
    ),
    "epochs": (
        "state",
        "revision",
        "catchup_history_id",
        "discovery_complete",
        "known_message_total",
    ),
    "epoch_partitions": (
        "state",
        "completed_pages",
        "observed_items",
        "page_token",
        "after_source_message_id",
        "revision",
    ),
    "source_events": ("source_thread_id", "processing", "revision", "error_code"),
    "history_checkpoints": (
        "cursor",
        "reliable_coverage_at",
        "revision",
        "active_poll_id",
    ),
    "history_polls": (
        "state",
        "completed_pages",
        "next_page_token",
        "final_history_id",
        "finished_at",
        "revision",
    ),
    "history_pages": ("complete",),
    "sync_jobs": (
        "state",
        "revision",
        "updated_at",
        "next_attempt_at",
        "attempt_count",
        "last_error_code",
    ),
    "job_claims": ("phase",),
    "insert_attempts": (
        "dispatch_started_at",
        "result_at",
        "semantic_digest",
        "semantic_version",
        "state",
        "certainty",
        "target_message_id",
        "target_thread_id",
        "attribution",
        "visibility",
        "verified_at",
        "error_code",
        "recovery_checks",
        "next_recovery_at",
        "revision",
    ),
    "message_mappings": (
        "mapping_revision",
        "attempt_id",
        "target_message_id",
        "target_thread_id",
        "verified_at",
        "visibility",
        "last_audit_at",
        "target_present",
    ),
    "mapping_history": ("superseded_at",),
    "thread_targets": ("anchor",),
    "action_commands": ("state", "cleanup", "executed_at", "error_code", "revision"),
    "thread_expansion_runs": ("current", "state", "completed_at", "revision"),
}


def _triggers():
    result = []
    for table in _IMMUTABLE_ROWS:
        result.extend(
            (
                _trigger(table + "_immutable_update", table, "UPDATE"),
                _trigger(table + "_immutable_delete", table, "DELETE"),
            )
        )
    for table in TABLES:
        if table.name not in _MUTABLE:
            continue
        columns = [
            column
            for column, _, _ in table.columns
            if column not in _MUTABLE[table.name]
        ]
        when = " OR ".join(f"OLD.{column} IS NOT NEW.{column}" for column in columns)
        result.append(
            _trigger(table.name + "_immutable_columns", table.name, "UPDATE", when)
        )
    for event in ("INSERT", "UPDATE", "DELETE"):
        parents = {"INSERT": ("NEW",), "DELETE": ("OLD",), "UPDATE": ("OLD", "NEW")}[
            event
        ]
        when = " OR ".join(
            "(SELECT sealed FROM rulesets WHERE "
            f"projection_id={parent}.projection_id AND "
            f"revision={parent}.ruleset_revision)=1"
            for parent in parents
        )
        result.append(
            _trigger(
                "ruleset_members_sealed_" + event.lower(),
                "ruleset_members",
                event,
                when,
            )
        )
    result.extend(
        (
            _trigger(
                "rulesets_unseal",
                "rulesets",
                "UPDATE",
                "OLD.sealed=1 AND NEW.sealed<>1",
            ),
            _trigger("rulesets_delete_sealed", "rulesets", "DELETE", "OLD.sealed=1"),
            _trigger(
                "mapping_history_resupersede",
                "mapping_history",
                "UPDATE",
                "OLD.superseded_at IS NOT NULL AND OLD.superseded_at IS NOT "
                "NEW.superseded_at",
            ),
            _trigger("mapping_history_delete", "mapping_history", "DELETE"),
            _trigger(
                "history_pages_uncomplete",
                "history_pages",
                "UPDATE",
                "OLD.complete=1 AND NEW.complete<>1",
            ),
            _trigger("history_pages_delete", "history_pages", "DELETE"),
            _trigger(
                "history_polls_terminal",
                "history_polls",
                "UPDATE",
                "OLD.state<>'reading'",
            ),
            _trigger(
                "history_polls_terminal_delete",
                "history_polls",
                "DELETE",
                "OLD.state<>'reading'",
            ),
            _trigger(
                "events_context_conflict",
                "source_events",
                "UPDATE",
                "OLD.source_thread_id IS NOT NULL AND OLD.source_thread_id IS NOT "
                "NEW.source_thread_id",
            ),
            _trigger(
                "expansion_current_monotonic",
                "thread_expansion_runs",
                "UPDATE",
                "OLD.current=0 AND NEW.current<>0",
            ),
            _trigger(
                "expansion_state_monotonic",
                "thread_expansion_runs",
                "UPDATE",
                "OLD.state<>NEW.state AND NOT(OLD.state='scanning' AND NEW.state "
                "IN('complete','needs_attention'))",
            ),
        )
    )
    for table in ("bindings", "binding_revisions"):
        for event in ("INSERT", "UPDATE"):
            when = (
                f"EXISTS(SELECT 1 FROM {table} b WHERE "
                "b.projection_id=NEW.projection_id AND b.role<>NEW.role AND "
                "(b.declared_address=NEW.declared_address OR "
                "(b.verified_address IS NOT NULL AND "
                "b.verified_address=NEW.verified_address)))"
            )
            result.append(
                _trigger(
                    table + "_different_accounts_" + event.lower(), table, event, when
                )
            )
    return tuple(result)


STATEMENTS = (
    tuple(_create(table) for table in TABLES)
    + tuple(
        f"CREATE {'UNIQUE ' if unique else ''}INDEX {name} ON "
        f"{table}({','.join(columns.split())})"
        + (f" WHERE {where}" if where is not None else "")
        for name, table, columns, unique, where in INDEXES
    )
    + _triggers()
)
