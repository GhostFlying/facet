"""Fixed fresh-v2 command catalogue; not an existing-state migration step."""

# The compiled SQL catalogue below intentionally keeps each predicate readable
# as provider-independent SQL; its long literals are not Python expressions.
# ruff: noqa: E501

from . import v0001

VERSION = 2

_COMMANDS = (
    "daemon_pause",
    "daemon_resume",
    "daemon_shutdown",
    "config_init",
    "facet_init",
    "auth_authorize",
    "auth_reauthorize",
    "backfill_preview",
    "backfill_start",
)


def _literal(values):
    return "(" + ",".join("'" + value + "'" for value in values) + ")"


def _column(name, kind, nullable=False):
    # Only fixed literals below reach this compiled builder. v0001 is unchanged.
    if kind == "Command":
        sqltype, predicate = "TEXT", f"{name} IN {_literal(_COMMANDS)}"
    elif kind == "Shutdown":
        sqltype, predicate = "TEXT", f"{name} IN('idle','requested','draining')"
    elif kind == "One":
        sqltype, predicate = "INTEGER", f"{name}=1"
    elif kind == "Request":
        sqltype, predicate = (
            "TEXT",
            (
                f"length(CAST({name} AS BLOB))=69 AND substr({name},1,4)='rq1_' "
                f"AND substr({name},37,1)='_' AND instr({name},char(0))=0 "
                f"AND substr({name},5,32) NOT GLOB '*[^0-9a-f]*' "
                f"AND substr({name},38,32) NOT GLOB '*[^0-9a-f]*' "
                f"AND substr({name},17,1)='4' AND substr({name},50,1)='4' "
                f"AND substr({name},21,1) IN('8','9','a','b') "
                f"AND substr({name},54,1) IN('8','9','a','b')"
            ),
        )
    else:
        sqltype, predicate = v0001._scalar(name, kind)
    if nullable:
        predicate = f"{name} IS NULL OR ({predicate})"
    return f"{name} {sqltype}{'' if nullable else ' NOT NULL'} CHECK({predicate})"


def _table(name, columns, extra):
    return (
        f"CREATE TABLE {name}("
        + ",".join(_column(*column) for column in columns)
        + ","
        + ",".join(extra)
        + ") STRICT"
    )


_PROJECTION_FK = (
    "FOREIGN KEY(projection_id) REFERENCES projections(projection_id) "
    "ON DELETE RESTRICT ON UPDATE RESTRICT"
)
_OPERATION_FK = (
    "FOREIGN KEY(projection_id,operation_id) "
    "REFERENCES operations(projection_id,operation_id) "
    "ON DELETE RESTRICT ON UPDATE RESTRICT"
)

_TABLES = (
    _table(
        "command_runtime",
        (
            ("projection_id", "P"),
            ("binding_guard", "R"),
            ("control_revision", "R"),
            ("owner_run_id", "L", True),
            ("shutdown_phase", "Shutdown"),
            ("shutdown_operation_id", "L", True),
            ("shutdown_owner_run_id", "L", True),
        ),
        (
            "PRIMARY KEY(projection_id)",
            _PROJECTION_FK,
            "FOREIGN KEY(projection_id,shutdown_operation_id) "
            "REFERENCES operations(projection_id,operation_id) "
            "ON DELETE RESTRICT ON UPDATE RESTRICT",
            "CHECK(binding_guard>=1)",
            "CHECK((shutdown_phase='idle' AND shutdown_operation_id IS NULL "
            "AND shutdown_owner_run_id IS NULL) OR "
            "(shutdown_phase IN('requested','draining') "
            "AND shutdown_operation_id IS NOT NULL AND shutdown_owner_run_id "
            "IS NOT NULL AND owner_run_id IS NOT NULL))",
        ),
    ),
    _table(
        "operations",
        (
            ("projection_id", "P"),
            ("operation_id", "L"),
            ("request_namespace", "L"),
            ("request_nonce", "L"),
            ("command", "Command"),
            ("payload_version", "One"),
            ("digest_version", "One"),
            ("digest", "H"),
            ("state", "OperationState"),
            ("revision", "R"),
            ("accepted_at", "T"),
            ("updated_at", "T"),
            ("completed_at", "T", True),
            ("code", "ErrorCode", True),
            ("effect_completed", "B"),
            ("expected_binding_revision", "R"),
            ("expected_config_revision", "R"),
            ("expected_preview_id", "L", True),
            ("confirmation_yes", "B"),
            ("duplicate_risk_acknowledged", "B"),
        ),
        (
            "PRIMARY KEY(projection_id,operation_id)",
            "UNIQUE(projection_id,request_namespace,request_nonce)",
            _PROJECTION_FK,
            "CHECK(revision>=1)",
            "CHECK((state IN('completed','rejected') AND completed_at IS NOT NULL) "
            "OR (state NOT IN('completed','rejected') AND completed_at IS NULL))",
            "CHECK(effect_completed=0 OR state='completed')",
            "CHECK(state<>'rejected' OR (code IS NOT NULL AND effect_completed=0))",
            "CHECK(state NOT IN('accepted','executing') OR code IS NULL)",
            "CHECK(updated_at>=accepted_at AND (completed_at IS NULL OR "
            "(completed_at>=accepted_at AND completed_at<=updated_at)))",
            "CHECK(((command='backfill_preview' AND expected_preview_id IS NULL "
            "AND confirmation_yes=0 AND duplicate_risk_acknowledged=0) OR "
            "(command='backfill_start' AND expected_preview_id IS NOT NULL "
            "AND confirmation_yes=1 AND duplicate_risk_acknowledged=0) OR "
            "(command NOT IN('backfill_preview','backfill_start') AND "
            "expected_preview_id IS NULL AND confirmation_yes=1 AND "
            "duplicate_risk_acknowledged=0)))",
        ),
    ),
    _table(
        "operation_controls",
        (
            ("projection_id", "P"),
            ("operation_id", "L"),
            ("before_paused", "B"),
            ("after_paused", "B"),
            ("before_control_revision", "R"),
            ("after_control_revision", "R"),
        ),
        (
            "PRIMARY KEY(projection_id,operation_id)",
            _PROJECTION_FK,
            _OPERATION_FK,
            "CHECK(after_control_revision=before_control_revision OR "
            "(before_control_revision<9223372036854775807 "
            "AND after_control_revision=before_control_revision+1))",
        ),
    ),
    _table(
        "operation_bootstrap",
        (
            ("projection_id", "P"),
            ("operation_id", "L"),
            ("config_semantic_digest", "H"),
            ("config_artifact_digest", "H"),
            ("bootstrap_request_id", "Request"),
            ("initialized_schema_version", "N", True),
        ),
        (
            "PRIMARY KEY(projection_id,operation_id)",
            _PROJECTION_FK,
            _OPERATION_FK,
            "CHECK(initialized_schema_version IS NULL "
            "OR initialized_schema_version>=1)",
        ),
    ),
    _table(
        "operation_auth",
        (
            ("projection_id", "P"),
            ("operation_id", "L"),
            ("role", "Role"),
            ("expected_credential_revision", "R"),
            ("expected_role_binding_revision", "R"),
            ("expected_policy_revision", "R"),
            ("supersedes_change_id", "L", True),
        ),
        (
            "PRIMARY KEY(projection_id,operation_id)",
            _PROJECTION_FK,
            _OPERATION_FK,
        ),
    ),
    _table(
        "operation_backfill",
        (
            ("projection_id", "P"),
            ("operation_id", "L"),
            ("purpose", "PreviewPurpose"),
            ("preview_operation_id", "L", True),
            ("ruleset_revision", "R"),
            ("window_start", "T"),
            ("window_end", "T"),
            ("discovery_cutoff", "T"),
            ("scope_digest", "H"),
            ("expires_at", "T"),
            ("invalidating_revision", "R"),
        ),
        (
            "PRIMARY KEY(projection_id,operation_id)",
            _PROJECTION_FK,
            _OPERATION_FK,
            "CHECK(window_start<window_end)",
            "CHECK(window_start<discovery_cutoff AND discovery_cutoff<window_end)",
            "CHECK(expires_at>=window_end)",
        ),
    ),
)

_INDEXES = (
    "CREATE INDEX operations_listing "
    "ON operations(projection_id,accepted_at,operation_id)",
    "CREATE INDEX operations_pending "
    "ON operations(projection_id,state,updated_at,operation_id)",
    "CREATE INDEX command_shutdown_reference "
    "ON command_runtime(projection_id,shutdown_operation_id)",
)


def _payload_guard(table, predicate):
    return (
        f"CREATE TRIGGER {table}_kind BEFORE INSERT ON {table} "
        "WHEN NOT EXISTS(SELECT 1 FROM operations o WHERE "
        "o.projection_id=NEW.projection_id AND o.operation_id=NEW.operation_id "
        f"AND ({predicate})) BEGIN SELECT RAISE(ABORT,'consistency_failure'); END"
    )


_PAYLOAD_GUARDS = (
    _payload_guard(
        "operation_controls",
        "o.command IN('daemon_pause','daemon_resume','daemon_shutdown') AND "
        "((o.state='completed' AND NEW.before_control_revision<9223372036854775807 "
        "AND NEW.after_control_revision=NEW.before_control_revision+1 "
        "AND ((o.command='daemon_pause' AND NEW.after_paused=1) OR "
        "(o.command='daemon_resume' AND NEW.after_paused=0) OR "
        "(o.command='daemon_shutdown' AND NEW.after_paused=NEW.before_paused))) OR "
        "(o.state='rejected' "
        "AND NEW.after_control_revision=NEW.before_control_revision "
        "AND NEW.after_paused=NEW.before_paused))",
    ),
    _payload_guard(
        "operation_bootstrap",
        "o.state='completed' AND o.effect_completed=1 AND o.code IS NULL "
        "AND o.expected_binding_revision=0 AND o.expected_config_revision=0 "
        "AND NEW.bootstrap_request_id="
        "'rq1_'||o.request_namespace||'_'||o.request_nonce "
        "AND ((o.command='config_init' AND NEW.initialized_schema_version IS NULL) "
        "OR (o.command='facet_init' AND NEW.initialized_schema_version IS NOT NULL))",
    ),
    _payload_guard(
        "operation_auth", "o.command IN('auth_authorize','auth_reauthorize')"
    ),
    _payload_guard(
        "operation_backfill",
        "o.command IN('backfill_preview','backfill_start') AND "
        "o.state IN('accepted','executing','completed') AND o.code IS NULL AND "
        "NEW.purpose='start_backfill' AND "
        "((o.command='backfill_preview' AND NEW.preview_operation_id IS NULL "
        "AND o.expected_preview_id IS NULL AND o.confirmation_yes=0) OR "
        "(o.command='backfill_start' AND NEW.preview_operation_id="
        "o.expected_preview_id AND EXISTS(SELECT 1 FROM operation_backfill p "
        "WHERE p.projection_id=o.projection_id AND p.operation_id="
        "NEW.preview_operation_id AND p.preview_operation_id IS NULL AND "
        "p.purpose='start_backfill' AND p.ruleset_revision=NEW.ruleset_revision "
        "AND p.window_start=NEW.window_start AND p.window_end=NEW.window_end "
        "AND p.discovery_cutoff=NEW.discovery_cutoff AND "
        "p.scope_digest=NEW.scope_digest AND p.expires_at=NEW.expires_at "
        "AND p.invalidating_revision=NEW.invalidating_revision)))",
    ),
)

_IMMUTABLE_COLUMNS = (
    "projection_id",
    "operation_id",
    "request_namespace",
    "request_nonce",
    "command",
    "payload_version",
    "digest_version",
    "digest",
    "accepted_at",
    "expected_binding_revision",
    "expected_config_revision",
    "expected_preview_id",
    "confirmation_yes",
    "duplicate_risk_acknowledged",
)
_IMMUTABILITY = (
    "CREATE TRIGGER operations_identity BEFORE UPDATE ON operations WHEN "
    + " OR ".join(f"NEW.{name} IS NOT OLD.{name}" for name in _IMMUTABLE_COLUMNS)
    + " BEGIN SELECT RAISE(ABORT,'consistency_failure'); END",
    "CREATE TRIGGER operations_retained BEFORE DELETE ON operations "
    "BEGIN SELECT RAISE(ABORT,'consistency_failure'); END",
) + tuple(
    f"CREATE TRIGGER {table}_{action.lower()}_immutable BEFORE {action} ON {table} "
    "BEGIN SELECT RAISE(ABORT,'consistency_failure'); END"
    for table in (
        "operation_controls",
        "operation_bootstrap",
        "operation_auth",
        "operation_backfill",
    )
    for action in ("UPDATE", "DELETE")
)

_BINDING_GUARD = (
    "CREATE TRIGGER command_binding_guard "
    "BEFORE UPDATE OF binding_revision ON bindings "
    "WHEN NEW.binding_revision<>OLD.binding_revision BEGIN "
    "SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM command_runtime "
    "WHERE projection_id=OLD.projection_id AND binding_guard<9223372036854775807) "
    "THEN RAISE(ABORT,'consistency_failure') END; "
    "UPDATE command_runtime SET binding_guard=binding_guard+1 "
    "WHERE projection_id=OLD.projection_id; END"
)

# Credential replacement metadata is deliberately a fresh-v2 extension.  It
# contains no secret/provider fields; the manager keeps those in the fixed
# owner-only role files.  The SQL is compiled here rather than assembled from
# configuration or arbitrary model dictionaries.
_CREDENTIAL_CHANGE_TABLE = """CREATE TABLE credential_changes(
projection_id TEXT NOT NULL CHECK(length(CAST(projection_id AS BLOB)) BETWEEN 1 AND 64 AND projection_id NOT GLOB '*[^A-Za-z0-9_-]*'),
state_instance_id TEXT NOT NULL CHECK(length(CAST(state_instance_id AS BLOB))=32 AND state_instance_id NOT GLOB '*[^0-9a-f]*'),
change_id TEXT NOT NULL CHECK(length(CAST(change_id AS BLOB))=32 AND change_id NOT GLOB '*[^0-9a-f]*'),
role TEXT NOT NULL CHECK(role IN('source','target')),
kind TEXT NOT NULL CHECK(kind IN('authorize','reauthorize','refresh')),
phase TEXT NOT NULL CHECK(phase IN('requesting','validated','committed','abandoned','attention')),
old_revision INTEGER NOT NULL CHECK(old_revision BETWEEN 0 AND 9223372036854775807),
new_revision INTEGER NOT NULL CHECK(new_revision BETWEEN 1 AND 9223372036854775807),
binding_revision INTEGER NOT NULL CHECK(binding_revision BETWEEN 1 AND 9223372036854775807),
scope_policy_revision INTEGER NOT NULL CHECK(scope_policy_revision BETWEEN 1 AND 9223372036854775807),
operation_id TEXT CHECK(operation_id IS NULL OR (length(CAST(operation_id AS BLOB))=32 AND operation_id NOT GLOB '*[^0-9a-f]*')),
supersedes_change_id TEXT CHECK(supersedes_change_id IS NULL OR (length(CAST(supersedes_change_id AS BLOB))=32 AND supersedes_change_id NOT GLOB '*[^0-9a-f]*')),
envelope_digest TEXT CHECK(envelope_digest IS NULL OR (length(CAST(envelope_digest AS BLOB))=64 AND envelope_digest NOT GLOB '*[^0-9a-f]*')),
scope_policy TEXT NOT NULL CHECK(scope_policy IN('source_readonly','source_convenience','target_default','target_labels')),
grant_kind TEXT CHECK(grant_kind IS NULL OR grant_kind IN('authorization_explicit','authorization_omitted_equal','refresh_explicit','refresh_omitted_inherited')),
granted_scopes TEXT CHECK(granted_scopes IS NULL OR length(CAST(granted_scopes AS BLOB)) BETWEEN 1 AND 128),
grant_parent_revision INTEGER CHECK(grant_parent_revision IS NULL OR grant_parent_revision BETWEEN 1 AND 9223372036854775807),
grant_observed_at INTEGER CHECK(grant_observed_at IS NULL OR grant_observed_at BETWEEN -62135596800000000 AND 253402300799999999),
profile_verified_at INTEGER NOT NULL CHECK(profile_verified_at BETWEEN -62135596800000000 AND 253402300799999999),
expires_at INTEGER NOT NULL CHECK(expires_at BETWEEN -62135596800000000 AND 253402300799999999),
started_at INTEGER NOT NULL CHECK(started_at BETWEEN -62135596800000000 AND 253402300799999999),
updated_at INTEGER NOT NULL CHECK(updated_at BETWEEN -62135596800000000 AND 253402300799999999),
error TEXT CHECK(error IS NULL OR error IN('invalid_input','unsupported_version','request_conflict','request_not_received','request_outcome_unknown','request_lineage_mismatch','confirmation_required','scope_required','binding_mismatch','binding_pending','preview_invalid','generation_stale','owner_unavailable','owner_busy','maintenance_incomplete','wait_timeout','source_auth_required','target_auth_required','source_rate_limited','target_rate_limited','network_unavailable','target_storage_full','insert_result_unknown','duplicate_candidates','attribution_unknown','fidelity_mismatch','source_missing','target_missing','database_unavailable','persistence_failure','consistency_failure','maintenance_required')),
PRIMARY KEY(projection_id,change_id),
FOREIGN KEY(projection_id) REFERENCES projections(projection_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
FOREIGN KEY(projection_id,role,binding_revision) REFERENCES binding_revisions(projection_id,role,binding_revision) ON DELETE RESTRICT ON UPDATE RESTRICT,
CHECK(new_revision=old_revision+1),
CHECK((kind='authorize' AND old_revision=0) OR (kind IN('reauthorize','refresh') AND old_revision>=1)),
CHECK(updated_at>=started_at),
CHECK((phase='requesting' AND envelope_digest IS NULL AND grant_kind IS NULL AND error IS NULL) OR
      (phase='validated' AND envelope_digest IS NOT NULL AND grant_kind IS NOT NULL AND error IS NULL) OR
      (phase='committed' AND envelope_digest IS NOT NULL AND grant_kind IS NOT NULL AND error IS NULL) OR
      (phase='abandoned' AND error IS NOT NULL) OR
      (phase='attention' AND error IS NOT NULL))
) STRICT"""

_CREDENTIAL_CHANGE_INDEX = (
    "CREATE UNIQUE INDEX credential_changes_open_role "
    "ON credential_changes(projection_id,role) "
    "WHERE phase IN('requesting','validated','attention')"
)

_CREDENTIAL_CHANGE_GUARDS = (
    "CREATE TRIGGER credential_changes_lineage BEFORE INSERT ON credential_changes "
    "WHEN NOT EXISTS(SELECT 1 FROM projections p WHERE "
    "p.projection_id=NEW.projection_id AND p.state_instance_id=NEW.state_instance_id) "
    "BEGIN SELECT RAISE(ABORT,'consistency_failure'); END",
    "CREATE TRIGGER credential_changes_operation BEFORE INSERT ON credential_changes "
    "WHEN NEW.operation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM operations o "
    "WHERE o.projection_id=NEW.projection_id AND o.operation_id=NEW.operation_id "
    "AND o.command IN('auth_authorize','auth_reauthorize')) "
    "BEGIN SELECT RAISE(ABORT,'consistency_failure'); END",
    "CREATE TRIGGER credential_changes_immutable BEFORE UPDATE ON credential_changes "
    "WHEN NEW.projection_id IS NOT OLD.projection_id OR NEW.state_instance_id IS NOT OLD.state_instance_id "
    "OR NEW.change_id IS NOT OLD.change_id OR NEW.role IS NOT OLD.role OR NEW.kind IS NOT OLD.kind "
    "OR NEW.old_revision IS NOT OLD.old_revision OR NEW.new_revision IS NOT OLD.new_revision "
    "OR NEW.binding_revision IS NOT OLD.binding_revision OR NEW.scope_policy_revision IS NOT OLD.scope_policy_revision "
    "OR NEW.operation_id IS NOT OLD.operation_id OR NEW.supersedes_change_id IS NOT OLD.supersedes_change_id "
    "OR NEW.started_at IS NOT OLD.started_at BEGIN SELECT RAISE(ABORT,'consistency_failure'); END",
    "CREATE TRIGGER credential_changes_delete BEFORE DELETE ON credential_changes "
    "BEGIN SELECT RAISE(ABORT,'consistency_failure'); END",
)

STATEMENTS = (
    _TABLES
    + (_CREDENTIAL_CHANGE_TABLE,)
    + _INDEXES
    + (_CREDENTIAL_CHANGE_INDEX,)
    + _PAYLOAD_GUARDS
    + _IMMUTABILITY
    + (_BINDING_GUARD,)
    + _CREDENTIAL_CHANGE_GUARDS
)
