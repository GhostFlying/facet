"""Owner-supplied connection adapters, not production filesystem/lock factories."""

import os
import sqlite3
import threading
from contextlib import suppress
from dataclasses import fields

from facet.contracts import (
    BindingState,
    ErrorCode,
    LocalId,
    ProjectionId,
    RestoreState,
    Role,
    Timestamp,
)

from .codecs import StorageFailure, encode_scalar, sqlite_failure, timestamp_to_sql
from .command_records import BootstrapInspection, FreshCommandBootstrap
from .migrations import CHECKSUMS, REGISTRY, REGISTRY_DIGEST, v0001
from .models import (
    BindingRow,
    BootstrapInitContext,
    OwnerSessionInfo,
    ProjectionRow,
    RulesetRow,
)
from .read_views import (
    _PERMITS,
    ReadViewPermit,
    _check_permit,
    _close_permit,
    _consume_permit,
)
from .schema import _inspect, _inspect_v1, _pristine
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
    __slots__ = ("_info", "_uow", "_creator_pid", "_creator_thread")

    def __init__(self, connection: sqlite3.Connection, info: OwnerSessionInfo):
        super().__init__(connection, info.state_instance_id)
        self._info = info
        self._uow = None
        self._creator_pid = os.getpid()
        self._creator_thread = threading.current_thread()

    def _check_creator(self) -> None:
        # Identity is available even after native connection failure. Refused
        # foreign/fork callers cannot probe, poison or clean up the real owner.
        if (
            os.getpid() != self._creator_pid
            or threading.current_thread() is not self._creator_thread
        ):
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)

    def _check(self) -> None:
        self._check_creator()
        super()._check()

    def _invalidate(self) -> None:
        self._check_creator()
        try:
            super()._invalidate()
        finally:
            if self._uow is not None:
                self._uow._retire()

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
    __slots__ = ("_permit",)

    def __new__(cls, *args, **kwargs):
        # A bound permit has exactly one admitted holder, allocated only by
        # _attach_view. An attached permit cannot construct another alias.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)

    def __init__(self, *args, **kwargs):
        # Do not permit direct reinitialization of the existing holder either.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)

    def __reduce__(self):
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)

    def __reduce_ex__(self, protocol):
        # Copy/deepcopy and pickle must not reconstruct a second holder or
        # traverse its private connection/capability state.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)

    def _check(self):
        # A wrong-thread/closed caller must not close or poison the real owner.
        if (
            self._closed
            or threading.current_thread() is not self._permit.creator_thread
        ):
            raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
        try:
            super()._check()
            _check_permit(self._permit)
        except StorageFailure:
            self._invalidate()
            raise

    def _invalidate(self):
        self._closed = True
        _close_permit(self._permit)

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
        # Keep an invalidation/owned-close failure outside the SQL rollback
        # handler: COMMIT already ended this snapshot and cleanup is one-shot.
        self._check()
        return result


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
    except BaseException as error:
        code = _command_code(error)
        # Native acknowledgement/close uncertainty never causes a second close
        # or permits a success/session. This path owns this supplied handle.
        try:
            connection.close()
        except BaseException:
            code = ErrorCode.PERSISTENCE_FAILURE
        _command_fail(code)


def _attach_view(
    connection: sqlite3.Connection,
    expected_instance: LocalId,
    *,
    permit: ReadViewPermit,
) -> ReadSession:
    if (
        type(expected_instance) is not LocalId
        or type(connection) is not sqlite3.Connection
    ):
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    consumed = False
    try:
        # All provenance and creator checks precede even connection-local SQL.
        _consume_permit(permit, connection, expected_instance)
        consumed = True
        if connection.autocommit is not True or connection.in_transaction:
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        # Provenance is consumed first, but unsupported v2 never configures a
        # read connection or becomes a ReadSession through generic inspection.
        if connection.execute("PRAGMA user_version").fetchone()[0] in {3, 4}:
            _inspect(connection)
        else:
            _inspect_v1(connection)
        # These are connection-local defenses, never journal/checkpoint PRAGMAs.
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = None
        if connection.execute("PRAGMA user_version").fetchone()[0] in {3, 4}:
            _inspect(connection)
        else:
            _inspect_v1(connection)
        if connection.execute(
            "SELECT state_instance_id FROM projections"
        ).fetchone() != (expected_instance.value,):
            raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)
        _check_permit(permit)
        session = object.__new__(ReadSession)
        _Session.__init__(session, connection, expected_instance)
        session._permit = permit
        return session
    except MemoryError:
        # First-consumption allocation failure owns cleanup, just like a schema
        # failure. There must not be an attached permit without its holder.
        if consumed:
            _close_permit(permit)
        raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE) from None
    except sqlite3.Error as error:
        _close_permit(permit)
        raise sqlite_failure(error) from None
    except StorageFailure as error:
        # Only this first attachment, or a still-bound exact handle, is ours.
        # A failed duplicate must never retire an already-admitted holder.
        # _close_permit repeats actual creator checks before closing, including
        # on pre-SQL lease failure; a foreign caller never adopts the owner.
        if (
            type(permit) is ReadViewPermit
            and permit in _PERMITS
            and permit.connection is connection
            and (consumed or permit.phase == "bound")
        ):
            _close_permit(permit)
        error.__cause__ = None
        error.__context__ = None
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


def _command_fail(code):
    try:
        raise StorageFailure(code) from None
    except StorageFailure as error:
        error.__cause__ = None
        error.__context__ = None
        raise


def _command_code(error):
    if type(error) is StorageFailure:
        return error.code
    if isinstance(error, sqlite3.Error):
        return sqlite_failure(error).code
    return ErrorCode.PERSISTENCE_FAILURE


def _v2_settings(connection):
    if type(connection) is not sqlite3.Connection or connection.autocommit is not True:
        raise StorageFailure(ErrorCode.INVALID_INPUT)
    if connection.in_transaction:
        raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise StorageFailure(ErrorCode.UNSUPPORTED_VERSION)
    for name, value in (
        ("journal_mode", "wal"),
        ("foreign_keys", 1),
        ("synchronous", 2),
        ("busy_timeout", 5000),
        ("trusted_schema", 0),
        ("wal_autocheckpoint", 1000),
        ("query_only", 0),
    ):
        if connection.execute(f"PRAGMA {name}").fetchone() != (value,):
            raise StorageFailure(ErrorCode.DATABASE_UNAVAILABLE)
    if connection.row_factory is not None:
        raise StorageFailure(ErrorCode.INVALID_INPUT)


def _v2_rollback_close(connection, begin_attempted, commit_attempted, code):
    # Armed BEFORE native BEGIN: a c_return fault can lose its acknowledgement
    # after SQLite really entered the transaction. Never retry BEGIN/COMMIT.
    if begin_attempted and not commit_attempted:
        try:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            if connection.in_transaction:
                code = ErrorCode.PERSISTENCE_FAILURE
        except BaseException:
            code = ErrorCode.PERSISTENCE_FAILURE
    try:
        connection.close()
    except BaseException:
        # An uncertain close is not retried; no metadata result/session escapes.
        code = ErrorCode.PERSISTENCE_FAILURE
    _command_fail(code)


def _initialize_database_v2(
    connection: sqlite3.Connection,
    *,
    bootstrap: BootstrapInitContext,
    initial_projection: ProjectionRow,
    source_binding: BindingRow,
    target_binding: BindingRow,
    initial_ruleset: RulesetRow,
    commands: FreshCommandBootstrap,
) -> WriterSession:
    """Storage only. The future genuine stopped issuer owns files/locks/journals."""
    from .command_store import _insert_bootstrap
    from .migrations import (
        FRESH_V2_CHECKSUMS,
        FRESH_V2_REGISTRY,
        FRESH_V2_REGISTRY_DIGEST,
    )

    begin_attempted = commit_attempted = attach_started = False
    owned = False
    try:
        if (
            type(connection) is not sqlite3.Connection
            or type(bootstrap) is not BootstrapInitContext
            or type(initial_projection) is not ProjectionRow
            or type(source_binding) is not BindingRow
            or type(target_binding) is not BindingRow
            or type(initial_ruleset) is not RulesetRow
            or type(commands) is not FreshCommandBootstrap
        ):
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        for row in (
            bootstrap,
            bootstrap.owner,
            initial_projection,
            source_binding,
            target_binding,
            initial_ruleset,
        ):
            type(row).__post_init__(row)
        FreshCommandBootstrap.__post_init__(commands)
        p, owner = initial_projection, bootstrap.owner
        bindings = source_binding, target_binding
        if (
            p.state_instance_id != owner.state_instance_id
            or p.request_namespace != owner.request_namespace
            or p.last_owner_run_id != owner.owner_run_id
            or p.singleton.value != 1
            or not p.daemon_paused
            or p.binding_state is not BindingState.VERIFICATION_PENDING
            or p.restore_state is not RestoreState.NORMAL
            or p.ruleset_revision.value != 0
            or p.config_revision.value != 0
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
            or commands.current.namespace != owner.request_namespace
            or commands.current.nonce != bootstrap.bootstrap_nonce
            or connection.autocommit is not True
            or connection.in_transaction
        ):
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        _pristine(connection)
        owned = True
        _configure_writer(connection, creating=True)
        begin_attempted = True
        connection.execute("BEGIN IMMEDIATE")
        for _, _, statements in FRESH_V2_REGISTRY:
            for statement in statements:
                connection.execute(statement)
        created = timestamp_to_sql(p.created_at)
        connection.execute(
            "INSERT INTO schema_metadata VALUES(1,2,?,?)",
            (FRESH_V2_REGISTRY_DIGEST, created),
        )
        for (version, name, _), checksum in zip(
            FRESH_V2_REGISTRY, FRESH_V2_CHECKSUMS, strict=True
        ):
            connection.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                (version, name, checksum, created),
            )
        _initial_insert(connection, "projections", p)
        _initial_insert(connection, "rulesets", initial_ruleset)
        for binding in bindings:
            values = tuple(
                encode_scalar(getattr(binding, f.name)) for f in fields(binding)
            )
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
        connection.execute(
            "INSERT INTO command_runtime VALUES(?,1,0,?,'idle',NULL,NULL)",
            (p.projection_id.value, owner.owner_run_id.value),
        )
        _insert_bootstrap(connection, p.projection_id, commands)
        connection.execute(f"PRAGMA application_id={v0001.APPLICATION_ID}")
        connection.execute("PRAGMA user_version=2")
        commit_attempted = True
        connection.execute("COMMIT")
        attach_started = True
        return _attach_writer(connection, owner)
    except BaseException as error:
        code = _command_code(error)
        if owned and not attach_started:
            _v2_rollback_close(connection, begin_attempted, commit_attempted, code)
        _command_fail(code)


def _begin_owner_session_v2(
    connection: sqlite3.Connection,
    *,
    owner: OwnerSessionInfo,
    expected_previous_run: LocalId | None,
    now: Timestamp,
) -> WriterSession:
    from .migrations import _FRESH_V2_MANIFEST, _FRESH_V3_MANIFEST, _FRESH_V4_MANIFEST
    from .schema import _inspect_manifest

    begin_attempted = commit_attempted = attach_started = False
    owned = False
    try:
        if (
            type(owner) is not OwnerSessionInfo
            or type(now) is not Timestamp
            or (
                expected_previous_run is not None
                and type(expected_previous_run) is not LocalId
            )
        ):
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        OwnerSessionInfo.__post_init__(owner)
        _v2_settings(connection)
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        manifest = {
            2: _FRESH_V2_MANIFEST,
            3: _FRESH_V3_MANIFEST,
            4: _FRESH_V4_MANIFEST,
        }.get(version)
        if manifest is None:
            raise StorageFailure(ErrorCode.MAINTENANCE_REQUIRED)
        _inspect_manifest(connection, manifest)
        row = connection.execute(
            "SELECT p.projection_id,p.state_instance_id,p.request_namespace,"
            "p.last_owner_run_id,c.owner_run_id FROM projections p "
            "JOIN command_runtime c USING(projection_id)"
        ).fetchall()
        previous = (
            None if expected_previous_run is None else expected_previous_run.value
        )
        if (
            len(row) != 1
            or row[0][1:]
            != (
                owner.state_instance_id.value,
                owner.request_namespace.value,
                previous,
                previous,
            )
            or owner.owner_run_id.value == previous
        ):
            raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)
        owned = True
        begin_attempted = True
        connection.execute("BEGIN IMMEDIATE")
        if (
            connection.execute(
                "UPDATE projections SET last_owner_run_id=? WHERE projection_id=? "
                "AND state_instance_id=? AND request_namespace=? "
                "AND last_owner_run_id IS ?",
                (
                    owner.owner_run_id.value,
                    row[0][0],
                    owner.state_instance_id.value,
                    owner.request_namespace.value,
                    previous,
                ),
            ).rowcount
            != 1
            or connection.execute(
                "UPDATE command_runtime SET owner_run_id=? "
                "WHERE projection_id=? AND owner_run_id IS ?",
                (owner.owner_run_id.value, row[0][0], previous),
            ).rowcount
            != 1
        ):
            raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)
        commit_attempted = True
        connection.execute("COMMIT")
        attach_started = True
        return _attach_writer(connection, owner)
    except BaseException as error:
        code = _command_code(error)
        if owned and not attach_started:
            _v2_rollback_close(connection, begin_attempted, commit_attempted, code)
        _command_fail(code)


def _inspect_bootstrap_v2(
    connection: sqlite3.Connection,
    *,
    projection_id: ProjectionId,
    namespace: LocalId,
    nonce: LocalId,
    prior_config_nonce: LocalId | None,
) -> BootstrapInspection:
    from .codecs import SchemaVersion
    from .command_store import _find_bootstrap
    from .migrations import _FRESH_V2_MANIFEST
    from .schema import _inspect_manifest

    owned = begin_attempted = commit_attempted = False
    try:
        if (
            type(projection_id) is not ProjectionId
            or type(namespace) is not LocalId
            or type(nonce) is not LocalId
            or (
                prior_config_nonce is not None
                and type(prior_config_nonce) is not LocalId
            )
            or prior_config_nonce == nonce
        ):
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        _v2_settings(connection)
        owned = True
        begin_attempted = True
        connection.execute("BEGIN")
        _inspect_manifest(connection, _FRESH_V2_MANIFEST)
        rows = connection.execute(
            "SELECT p.state_instance_id,p.request_namespace,"
            "p.last_owner_run_id,c.owner_run_id "
            "FROM projections p JOIN command_runtime c USING(projection_id) "
            "WHERE p.projection_id=? LIMIT 2",
            (projection_id.value,),
        ).fetchall()
        if (
            len(rows) != 1
            or rows[0][1] != namespace.value
            or (rows[0][2] is None or rows[0][2] != rows[0][3])
        ):
            raise StorageFailure(ErrorCode.REQUEST_LINEAGE_MISMATCH)
        owner = OwnerSessionInfo(
            LocalId(rows[0][2]), LocalId(rows[0][0]), LocalId(rows[0][1])
        )
        current = _find_bootstrap(connection, projection_id, namespace, nonce)
        prior = (
            (None, None)
            if prior_config_nonce is None
            else _find_bootstrap(
                connection, projection_id, namespace, prior_config_nonce
            )
        )
        result = BootstrapInspection(SchemaVersion(2), owner, *current, *prior)
        commit_attempted = True
        connection.execute("COMMIT")
        return result
    except BaseException as error:
        code = _command_code(error)
        if owned:
            _v2_rollback_close(connection, begin_attempted, commit_attempted, code)
        _command_fail(code)
