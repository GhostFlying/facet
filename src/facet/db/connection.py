"""Owner-supplied connection adapters, not production filesystem/lock factories."""

import sqlite3
import threading
from contextlib import suppress
from dataclasses import fields

from facet.contracts import (
    BindingState,
    ErrorCode,
    LocalId,
    RestoreState,
    Role,
)

from .codecs import StorageFailure, encode_scalar, sqlite_failure, timestamp_to_sql
from .migrations import CHECKSUMS, REGISTRY, REGISTRY_DIGEST, v0001
from .models import (
    BindingRow,
    BootstrapInitContext,
    OwnerSessionInfo,
    ProjectionRow,
    RulesetRow,
)
from .schema import _inspect, _pristine
from .transactions import UnitOfWork


def _configure_writer(connection: sqlite3.Connection, *, creating: bool) -> None:
    if (
        not isinstance(connection, sqlite3.Connection)
        or connection.autocommit is not True
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    if connection.in_transaction:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise StorageFailure(ErrorCode.UNSUPPORTED_VERSION)
    if creating:
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    else:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    if mode != "wal":
        # In-memory connections are not a substitute for the local WAL gate.
        raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
    for name, value in (
        ("foreign_keys", 1),
        ("synchronous", 2),
        ("busy_timeout", 5000),
        ("trusted_schema", 0),
        ("wal_autocheckpoint", 1000),
    ):
        connection.execute(f"PRAGMA {name}={value}")
        if connection.execute(f"PRAGMA {name}").fetchone()[0] != value:
            raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
    connection.row_factory = None


class _Session:
    __slots__ = ("_connection", "_thread", "_closed", "_instance")

    def __init__(self, connection: sqlite3.Connection, instance: LocalId):
        self._connection = connection
        self._thread = threading.get_ident()
        self._closed = False
        self._instance = instance

    def _check(self) -> None:
        if self._closed or threading.get_ident() != self._thread:
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
        try:
            _ = self._connection.in_transaction
        except sqlite3.Error:
            self._closed = True
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE) from None

    def _invalidate(self) -> None:
        self._closed = True
        with suppress(sqlite3.Error):
            self._connection.close()

    def close(self) -> None:
        self._check()
        self._invalidate()


class WriterSession(_Session):
    __slots__ = ("_info", "_uow")

    def __init__(self, connection: sqlite3.Connection, info: OwnerSessionInfo):
        super().__init__(connection, info.state_instance_id)
        self._info = info
        self._uow = None

    def _check_lineage(self) -> None:
        row = self._connection.execute(
            "SELECT state_instance_id,request_namespace,last_owner_run_id "
            "FROM projections"
        ).fetchone()
        expected = (
            self._info.state_instance_id.value,
            self._info.request_namespace.value,
            self._info.owner_run_id.value,
        )
        if row != expected:
            raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)

    def transaction(self) -> UnitOfWork:
        self._check()
        return UnitOfWork(self)

    def _relational_guards(self) -> None:
        # Claims are ephemeral but their shape/state/revision must agree at the
        # composed transaction boundary. Phase changes retain acquisition rev.
        bad = self._connection.execute(
            "SELECT 1 FROM sync_jobs j LEFT JOIN job_claims c "
            "ON c.projection_id=j.projection_id AND c.job_id=j.job_id "
            "LEFT JOIN insert_attempts a ON a.projection_id=j.projection_id "
            "AND a.attempt_id=j.attempt_id "
            "WHERE (j.state='claimed' AND c.job_id IS NULL) OR "
            "(j.state<>'claimed' AND c.job_id IS NOT NULL) OR "
            "(c.job_revision>j.revision) OR "
            "((CASE WHEN j.kind='recover_insert' THEN a.generation "
            "ELSE j.generation END) IS NOT c.thread_generation "
            "AND c.job_id IS NOT NULL) "
            "LIMIT 1"
        ).fetchone()
        if bad is not None:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)


class ReadSession(_Session):
    __slots__ = ()

    def _read(self, sql: str, parameters: tuple = (), *, maximum: int = 500) -> tuple:
        self._check()
        connection = self._connection
        if connection.in_transaction:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        try:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT state_instance_id FROM projections"
            ).fetchone()
            if row != (self._instance.value,):
                raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)
            result = tuple(connection.execute(sql, parameters).fetchmany(maximum + 1))
            if len(result) > maximum:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            connection.execute("COMMIT")
            return result
        except (sqlite3.Error, StorageFailure) as error:
            try:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
            except sqlite3.Error:
                self._invalidate()
                raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE) from None
            if isinstance(error, StorageFailure):
                raise error from None
            raise sqlite_failure(error) from None


def _attach_writer(
    connection: sqlite3.Connection, info: OwnerSessionInfo
) -> WriterSession:
    if type(info) is not OwnerSessionInfo or not isinstance(
        connection, sqlite3.Connection
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    try:
        _inspect(connection)
        _configure_writer(connection, creating=False)
        session = WriterSession(connection, info)
        session._check_lineage()
        return session
    except sqlite3.Error as error:
        connection.close()
        raise sqlite_failure(error) from None
    except StorageFailure:
        connection.close()
        raise


def _attach_view(
    connection: sqlite3.Connection, expected_instance: LocalId
) -> ReadSession:
    if type(expected_instance) is not LocalId or not isinstance(
        connection, sqlite3.Connection
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    try:
        if connection.autocommit is not True or connection.in_transaction:
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        # These are connection-local defenses, never journal/checkpoint PRAGMAs.
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = None
        _inspect(connection)
        if connection.execute(
            "SELECT state_instance_id FROM projections"
        ).fetchone() != (expected_instance.value,):
            raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)
        return ReadSession(connection, expected_instance)
    except sqlite3.Error as error:
        connection.close()
        raise sqlite_failure(error) from None
    except StorageFailure:
        connection.close()
        raise


def _initialize_database(
    connection: sqlite3.Connection,
    *,
    bootstrap: BootstrapInitContext,
    initial_projection: ProjectionRow,
    source_binding: BindingRow,
    target_binding: BindingRow,
    initial_ruleset: RulesetRow,
) -> WriterSession:
    """Only the real M1-03 bootstrap journal/locks can call this in production."""
    if (
        not isinstance(connection, sqlite3.Connection)
        or type(bootstrap) is not BootstrapInitContext
        or type(initial_projection) is not ProjectionRow
        or type(source_binding) is not BindingRow
        or type(target_binding) is not BindingRow
        or type(initial_ruleset) is not RulesetRow
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    p, owner = initial_projection, bootstrap.owner
    bindings = (source_binding, target_binding)
    if (
        p.state_instance_id != owner.state_instance_id
        or p.request_namespace != owner.request_namespace
        or p.last_owner_run_id != owner.owner_run_id
        or p.singleton.value != 1
        or not p.daemon_paused
        or p.binding_state is not BindingState.VERIFICATION_PENDING
        or p.restore_state is not RestoreState.NORMAL
        or p.ruleset_revision.value != 0
        or initial_ruleset.projection_id != p.projection_id
        or initial_ruleset.revision.value != 0
        or not initial_ruleset.sealed
        or tuple(b.role for b in bindings) != (Role.SOURCE, Role.TARGET)
        or source_binding.declared_address == target_binding.declared_address
        or any(
            b.projection_id != p.projection_id
            or b.verified_address is not None
            or b.verified_at is not None
            or b.credential_revision.value != 0
            or b.binding_revision.value != 1
            or b.state is not BindingState.VERIFICATION_PENDING
            for b in bindings
        )
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    try:
        _pristine(connection)
        _configure_writer(connection, creating=True)
        connection.execute("BEGIN IMMEDIATE")
        for statement in v0001.STATEMENTS:
            connection.execute(statement)
        created = timestamp_to_sql(p.created_at)
        connection.execute(
            "INSERT INTO schema_metadata VALUES(1,1,?,?)", (REGISTRY_DIGEST, created)
        )
        for (version, name, _), checksum in zip(REGISTRY, CHECKSUMS, strict=True):
            connection.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                (
                    version,
                    name,
                    checksum,
                    created,
                ),
            )
        _initial_insert(connection, "projections", p)
        _initial_insert(connection, "rulesets", initial_ruleset)
        for binding in bindings:
            values = tuple(
                encode_scalar(getattr(binding, f.name)) for f in fields(binding)
            )
            # History order is role/revision BEFORE address, unlike current row.
            connection.execute(
                "INSERT INTO binding_revisions VALUES(?,?,?,?,?,?,?)",
                (
                    values[0],
                    values[1],
                    values[5],
                    values[2],
                    values[3],
                    values[6],
                    values[7],
                ),
            )
            _initial_insert(connection, "bindings", binding)
        connection.execute(
            "INSERT INTO history_checkpoints VALUES(?,NULL,NULL,0,NULL)",
            (p.projection_id.value,),
        )
        connection.execute(f"PRAGMA application_id={v0001.APPLICATION_ID}")
        connection.execute("PRAGMA user_version=1")
        connection.execute("COMMIT")
        return _attach_writer(connection, owner)
    except sqlite3.Error as error:
        connection.close()
        raise sqlite_failure(error) from None
    except StorageFailure:
        connection.close()
        raise


def _initial_insert(connection, table, row):
    # A private finite bootstrap helper, not an arbitrary-row write endpoint.
    expected = {
        "projections": ProjectionRow,
        "rulesets": RulesetRow,
        "bindings": BindingRow,
    }
    if table not in expected or type(row) is not expected[table]:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    values = tuple(encode_scalar(getattr(row, f.name)) for f in fields(row))
    connection.execute(
        f"INSERT INTO {table} VALUES({','.join('?' for _ in values)})", values
    )
