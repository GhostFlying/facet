"""Private fixed repository building blocks; no arbitrary-row public operation."""

from functools import wraps

from facet.contracts import ErrorCode, LocalId, ProjectionId, ProviderId, Revision, Role

from ..codecs import KeyBytes, StorageFailure, encode_scalar, invalid
from ..connection import ReadSession
from ..migrations.v0001 import TABLES
from ..models import RevisionGuard, WriteReceipt
from ..transactions import UnitOfWork
from .serialization import COLUMNS, ROW_CLASSES, _decode_row, _encode_row

_SELECTOR_TYPES = {
    "P": ProjectionId,
    "L": LocalId,
    "V": ProviderId,
    "R": Revision,
    "Role": Role,
    "KeyBytes": KeyBytes,
}
_SELECTOR_FIELDS = {
    table.name: {name: _SELECTOR_TYPES.get(kind) for name, kind, _ in table.columns}
    for table in TABLES
}


def _mutating(function):
    @wraps(function)
    def call(uow, projection_id, *args, **kwargs):
        # Establish an exact, active, current-thread owner before touching its
        # failure flag. Invalid objects or another thread must not poison it.
        if type(uow) is not UnitOfWork:
            invalid()
        uow._check()
        try:
            _context(uow, projection_id, writing=True)
            return function(uow, projection_id, *args, **kwargs)
        except StorageFailure:
            uow._failed = True
            raise
        except (ValueError, TypeError, AttributeError, KeyError):
            uow._failed = True
            raise StorageFailure(ErrorCode.INVALID_INPUT) from None

    return call


def _context(context, projection, *, writing=False):
    if type(projection) is not ProjectionId:
        invalid()
    if type(context) is UnitOfWork or not writing and type(context) is ReadSession:
        context._check()
    else:
        invalid()


def _query(context, sql, parameters=(), *, maximum=500):
    if type(context) is UnitOfWork:
        rows = tuple(context._execute(sql, parameters).fetchmany(maximum + 1))
        if len(rows) > maximum:
            raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
        return rows
    return context._read(sql, parameters, maximum=maximum)


def _get(context, projection, table, selectors):
    _context(context, projection)
    if table not in ROW_CLASSES:
        invalid()
    columns = COLUMNS[table]
    clauses = ["projection_id=?"]
    params = [projection.value]
    for name, value in selectors:
        if name not in columns:
            invalid()
        if (
            _SELECTOR_FIELDS[table].get(name) is None
            or type(value) is not _SELECTOR_FIELDS[table][name]
        ):
            invalid()
        clauses.append(name + "=?")
        params.append(encode_scalar(value))
    rows = _query(
        context,
        "SELECT "
        + ",".join(columns)
        + " FROM "
        + table
        + " WHERE "
        + " AND ".join(clauses),
        tuple(params),
        maximum=1,
    )
    if not rows:
        return None
    return _decode(context, projection, table, rows[0])


def _decode(context, projection, table, values):
    event, partition = None, None
    if table == "sync_jobs":
        raw = dict(zip(COLUMNS[table], values, strict=True))
        if raw["event_id"] is not None:
            from facet.contracts import LocalId

            related = _get(
                context,
                projection,
                "source_events",
                (("event_id", LocalId(raw["event_id"])),),
            )
            if related is None:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            event = related.event.key
        if raw["partition_key"] is not None:
            from facet.contracts import LocalId

            from ..codecs import KeyBytes

            related = _get(
                context,
                projection,
                "epoch_partitions",
                (
                    ("epoch_id", LocalId(raw["partition_epoch_id"])),
                    ("partition_key", KeyBytes(raw["partition_key"])),
                ),
            )
            if related is None:
                raise StorageFailure(ErrorCode.CONSISTENCY_FAILURE)
            partition = related.progress.partition
    return _decode_row(table, values, event=event, partition=partition)


def _require_row(projection, table, row):
    if table not in ROW_CLASSES or type(row) is not ROW_CLASSES[table]:
        invalid()
    if row.projection_id != projection:
        invalid()


def _insert(uow, projection, table, row, *, event_id=None):
    _require_row(projection, table, row)
    values = _encode_row(table, row, event_id=event_id)
    uow._execute(
        "INSERT INTO "
        + table
        + "("
        + ",".join(COLUMNS[table])
        + ") VALUES("
        + ",".join("?" for _ in values)
        + ")",
        values,
    )


def _guard(actual, guard):
    if type(guard) is not RevisionGuard:
        invalid()
    if actual != guard.expected:
        raise StorageFailure(ErrorCode.REQUEST_CONFLICT)


def _batch(rows, cls):
    if (
        type(rows) is not tuple
        or len(rows) > 500
        or any(type(r) is not cls for r in rows)
    ):
        invalid()


def _receipt(row, disposition="created", *, id_field, revision_field="revision"):
    return WriteReceipt(
        disposition,
        getattr(row, id_field),
        getattr(row, revision_field) if revision_field else Revision(0),
    )


def _conflict():
    raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
