"""Fixed fresh-v2 command catalogue; not an existing-state migration step."""

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
            "CHECK(expected_preview_id IS NULL AND confirmation_yes=1 "
            "AND duplicate_risk_acknowledged=0)",
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
    for table in ("operation_controls", "operation_bootstrap", "operation_auth")
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

STATEMENTS = _TABLES + _INDEXES + _PAYLOAD_GUARDS + _IMMUTABILITY + (_BINDING_GUARD,)
