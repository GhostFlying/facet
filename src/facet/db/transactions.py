"""Short explicit transactions. No callback, savepoint, network wait, or retry."""

import sqlite3
from typing import TYPE_CHECKING

from facet.contracts import ErrorCode

from .codecs import StorageFailure, sqlite_failure

if TYPE_CHECKING:
    from .connection import WriterSession


class UnitOfWork:
    __slots__ = (
        "_session",
        "_entered",
        "_active",
        "_failed",
        "_action_scope",
        "_action_business_touched",
        "_action_attention_completed",
    )

    def __init__(self, session: "WriterSession"):
        self._session = session
        self._entered = False
        self._active = False
        self._failed = False
        self._action_scope = None
        self._action_business_touched = False
        self._action_attention_completed = False

    def __enter__(self) -> "UnitOfWork":
        session = self._session
        session._check()
        if (
            self._entered
            or session._uow is not None
            or session._connection.in_transaction
        ):
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        self._entered = True
        try:
            session._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise sqlite_failure(error) from None
        self._active = True
        self._action_scope = None
        self._action_business_touched = False
        self._action_attention_completed = False
        session._uow = self
        try:
            session._check_lineage()
        except (StorageFailure, sqlite3.Error) as error:
            self._rollback()
            if isinstance(error, StorageFailure):
                raise
            raise sqlite_failure(error) from None
        return self

    def _check(self) -> None:
        self._session._check()
        if not self._active or self._session._uow is not self or self._failed:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)

    def _execute(self, sql: str, parameters: tuple = ()) -> sqlite3.Cursor:
        """Only fixed internal repository SQL calls this private helper."""
        self._check()
        try:
            return self._session._connection.execute(sql, parameters)
        except sqlite3.Error as error:
            self._failed = True
            raise sqlite_failure(error) from None

    def _rollback(self) -> None:
        session = self._session
        try:
            session._connection.execute("ROLLBACK")
        except sqlite3.Error:
            session._invalidate()
            raise StorageFailure(ErrorCode.PERSISTENCE_FAILURE) from None
        finally:
            from .repositories.actions import _invalidate_action_scope

            _invalidate_action_scope(self)
            self._active = False
            session._uow = None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        session = self._session
        try:
            session._check()
        except StorageFailure:
            from .repositories.actions import _invalidate_action_scope

            _invalidate_action_scope(self)
            raise
        if not self._active:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        if exc_type is not None or self._failed:
            self._rollback()
            if isinstance(exc, StorageFailure):
                return False
            if isinstance(exc, sqlite3.Error):
                raise sqlite_failure(exc) from None
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE) from None
        try:
            from .repositories.actions import _validate_action_commit

            _validate_action_commit(self)
            session._relational_guards()
        except (StorageFailure, sqlite3.Error) as error:
            self._rollback()
            if isinstance(error, StorageFailure):
                raise
            raise sqlite_failure(error) from None
        try:
            session._connection.execute("COMMIT")
        except sqlite3.Error as error:
            # A failed/ambiguous commit never permits another write or a success
            # receipt on this connection, even when a rollback appears to work.
            session._invalidate()
            raise sqlite_failure(error) from None
        finally:
            from .repositories.actions import _invalidate_action_scope

            _invalidate_action_scope(self)
            self._active = False
            session._uow = None
        return False
