"""Bounded serial thread expansion and insert execution, with no raw cache."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from facet.contracts import (
    Claim,
    ClaimPhase,
    Count,
    DatePolicy,
    ErrorCode,
    InsertState,
    JobKind,
    JobState,
    LocalId,
    OutcomeCertainty,
    PartitionState,
    Revision,
    Role,
    Timestamp,
    Visibility,
)
from facet.contracts.records import JobSubjectProjectMessage
from facet.db.codecs import (
    AttributionKind,
    ExpansionItemKind,
    StorageFailure,
    next_revision,
    timestamp_to_sql,
)
from facet.db.keys import expansion_digest, job_key
from facet.db.models import (
    InsertAttemptRow,
    MappingHistoryRow,
    MessageMappingRow,
    RevisionGuard,
    SyncJobRow,
    TargetOwnershipRow,
    ThreadExpansionItemRow,
    ThreadExpansionRunRow,
    ThreadTargetRow,
)
from facet.db.repositories import expansion, intents, jobs, mappings
from facet.db.repositories.base import _decode, _get, _query
from facet.db.repositories.serialization import COLUMNS
from facet.gmail.retry import ProviderFailure

from .fidelity import inspect


def _now():
    return Timestamp(datetime.now(UTC))


def _id():
    return LocalId(uuid4().hex)


@dataclass(frozen=True, slots=True)
class WorkerReceipt:
    processed: int = 0
    expanded: int = 0
    verified: int = 0
    deferred: int = 0
    recovery: int = 0
    cancelled: int = 0


class ProjectionWorker:
    """One owner executes at most ``max_jobs``; recovery jobs are not selected."""

    def __init__(self, owner, source, target, *, max_raw_bytes=35_000_000):
        if type(max_raw_bytes) is not int or not 1 <= max_raw_bytes <= 35_000_000:
            raise ValueError("invalid_input")
        self._owner = owner
        self._source = source
        self._target = target
        self._max_raw_bytes = max_raw_bytes
        self._projection = owner.projection_id

    def run(self, *, max_jobs=1):
        if type(max_jobs) is not int or not 1 <= max_jobs <= 10_000:
            raise ValueError("invalid_input")
        counts = {field: 0 for field in WorkerReceipt.__dataclass_fields__}
        for _ in range(max_jobs):
            job = self._claim_next()
            if job is None:
                break
            counts["processed"] += 1
            try:
                outcome = (
                    self._expand(job)
                    if job.kind is JobKind.EXPAND_THREAD
                    else self._project(job)
                )
            except ProviderFailure as error:
                self._defer(job, error.code, error.retry_after_seconds)
                outcome = "deferred"
            except (KeyError, TypeError, ValueError):
                self._defer(job, ErrorCode.INVALID_INPUT)
                outcome = "deferred"
            except StorageFailure as error:
                if error.code is ErrorCode.GENERATION_STALE:
                    # stop_thread already cancelled unstarted jobs and prepared
                    # attempts atomically. Never revive them with a retry.
                    outcome = "cancelled"
                elif error.code in {
                    ErrorCode.DATABASE_UNAVAILABLE,
                    ErrorCode.PERSISTENCE_FAILURE,
                    ErrorCode.CONSISTENCY_FAILURE,
                }:
                    raise
                else:
                    # Repository conflicts are durable attention, not a reason
                    # to leave a claimed job orphaned.
                    self._defer(job, error.code)
                    outcome = "deferred"
            counts[outcome] += 1
        return WorkerReceipt(**counts)

    def _claim_next(self):
        now = _now()
        with self._owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT "
                + ",".join("j." + col for col in COLUMNS["sync_jobs"])
                + " FROM sync_jobs j JOIN tracked_threads t ON "
                "t.projection_id=j.projection_id "
                "AND t.source_thread_id=j.source_thread_id "
                "WHERE j.projection_id=? "
                "AND j.kind IN('expand_thread','project_message') "
                "AND j.state IN('queued','retry_wait') AND "
                "(j.next_attempt_at IS NULL OR j.next_attempt_at<=?) "
                "AND t.active=1 AND t.generation=j.generation "
                "ORDER BY j.created_at,j.job_id LIMIT 1",
                (self._projection.value, timestamp_to_sql(now)),
                maximum=1,
            )
            if not rows:
                return None
            job = _decode(uow, self._projection, "sync_jobs", rows[0])
            acquired = Claim(
                _id(),
                self._owner.owner_info.owner_run_id,
                now,
                job.subject.generation,
                next_revision(job.revision),
                ClaimPhase.PREPARING,
            )
            jobs.claim(
                uow,
                self._projection,
                job.job_id,
                acquired,
                RevisionGuard(job.revision),
                now,
            )
            return _get(uow, self._projection, "sync_jobs", (("job_id", job.job_id),))

    def _defer(self, job, code, retry_seconds=None):
        if code is ErrorCode.SOURCE_MISSING:
            state, retry = "source_missing", None
        elif code in {
            ErrorCode.SOURCE_AUTH_REQUIRED,
            ErrorCode.TARGET_AUTH_REQUIRED,
            ErrorCode.SOURCE_RATE_LIMITED,
            ErrorCode.TARGET_RATE_LIMITED,
            ErrorCode.NETWORK_UNAVAILABLE,
            ErrorCode.TARGET_STORAGE_FULL,
        }:
            state = "retry_wait"
            retry = Timestamp(
                _now().value + timedelta(seconds=max(1, retry_seconds or 60))
            )
        else:
            state, retry = "needs_attention", None
        with self._owner.session.transaction() as uow:
            current = _get(
                uow, self._projection, "sync_jobs", (("job_id", job.job_id),)
            )
            if current.state is JobState.CANCELLED:
                return
            jobs.defer_job(
                uow,
                self._projection,
                job.job_id,
                state,
                code,
                retry,
                RevisionGuard(current.revision),
            )

    def _expand(self, job):
        try:
            metadata = self._source.thread_metadata(job.subject.source_thread_id)
        except ProviderFailure as error:
            if error.status == 404:
                raise error.with_code(
                    ErrorCode.SOURCE_MISSING, role=Role.SOURCE
                ) from None
            raise
        if metadata.thread_id != job.subject.source_thread_id:
            raise ValueError("invalid_input")
        selected = tuple(
            sorted(
                (
                    message
                    for message in metadata.messages
                    if "DRAFT" not in message.labels
                ),
                key=lambda message: (
                    message.internal_date,
                    message.message_id.value.encode(),
                ),
            )
        )
        if len({message.message_id for message in selected}) != len(selected) or any(
            message.thread_id != metadata.thread_id for message in selected
        ):
            raise ValueError("invalid_input")
        now = _now()
        with self._owner.session.transaction() as uow:
            self._active(uow, job)
            run = ThreadExpansionRunRow(
                self._projection,
                _id(),
                job.job_id,
                job.subject.source_thread_id,
                job.subject.epoch_id,
                job.subject.generation,
                True,
                PartitionState.SCANNING,
                expansion_digest(tuple(message.message_id for message in selected)),
                Count(len(selected)),
                now,
                None,
                Revision(0),
            )
            receipt = expansion.begin_expansion(
                uow, self._projection, run, RevisionGuard(job.revision)
            )
            run_id, revision = receipt.object_id, receipt.revision
            items, children = [], []
            for ordinal, message in enumerate(selected):
                mapped = _get(
                    uow,
                    self._projection,
                    "message_mappings",
                    (("source_message_id", message.message_id),),
                )
                if mapped is not None:
                    items.append(
                        ThreadExpansionItemRow(
                            self._projection,
                            run_id,
                            message.message_id,
                            ExpansionItemKind.VERIFIED_MAPPING,
                            None,
                            mapped.source_message_id,
                            mapped.mapping_revision,
                        )
                    )
                    continue
                subject = JobSubjectProjectMessage(
                    "project_message",
                    message.message_id,
                    metadata.thread_id,
                    job.subject.generation,
                )
                created = Timestamp(now.value + timedelta(microseconds=ordinal))
                child = SyncJobRow(
                    self._projection,
                    _id(),
                    JobKind.PROJECT_MESSAGE,
                    Count(1),
                    job_key(self._projection, subject),
                    job.priority,
                    JobState.QUEUED,
                    Revision(0),
                    created,
                    created,
                    None,
                    Count(0),
                    None,
                    job.subject.epoch_id,
                    subject,
                )
                children.append(child)
                items.append(
                    ThreadExpansionItemRow(
                        self._projection,
                        run_id,
                        message.message_id,
                        ExpansionItemKind.PROJECT_JOB,
                        child.job_id,
                        None,
                        None,
                    )
                )
            for offset in range(0, len(items), 500):
                chunk = tuple(items[offset : offset + 500])
                child_ids = {item.project_job_id for item in chunk}
                receipt = expansion.ingest_expansion_items(
                    uow,
                    self._projection,
                    run_id,
                    chunk,
                    tuple(child for child in children if child.job_id in child_ids),
                    RevisionGuard(revision),
                )
                revision = receipt.revision
            expansion.finish_expansion(
                uow, self._projection, run_id, _now(), RevisionGuard(revision)
            )
            jobs.complete_noninsert_job(
                uow, self._projection, job.job_id, RevisionGuard(job.revision)
            )
        return "expanded"

    def _project(self, job):
        try:
            raw = self._source.raw(job.subject.source_message_id)
        except ProviderFailure as error:
            if error.status == 404:
                raise error.with_code(
                    ErrorCode.SOURCE_MISSING, role=Role.SOURCE
                ) from None
            raise
        if len(raw) > self._max_raw_bytes:
            raise ValueError("invalid_input")
        facts = inspect(raw)
        with self._owner.session.transaction() as uow:
            self._active(uow, job)
            claim = _get(uow, self._projection, "job_claims", (("job_id", job.job_id),))
            binding = _get(uow, self._projection, "bindings", (("role", Role.TARGET),))
            anchors = _query(
                uow,
                "SELECT "
                + ",".join(COLUMNS["thread_targets"])
                + " FROM thread_targets WHERE projection_id=? "
                "AND source_thread_id=? AND anchor=1",
                (self._projection.value, job.subject.source_thread_id.value),
                maximum=1,
            )
            anchor = (
                _decode(uow, self._projection, "thread_targets", anchors[0])
                if anchors
                else None
            )
            attempt = InsertAttemptRow(
                self._projection,
                _id(),
                job.job_id,
                claim.claim.claim_id,
                job.subject.source_message_id,
                job.subject.source_thread_id,
                job.subject.generation,
                Role.TARGET,
                binding.binding_revision,
                _now(),
                None,
                None,
                anchor.target_thread_id if anchor else None,
                facts.raw_digest,
                None,
                None,
                facts.rfc_message_id,
                facts.date_policy,
                InsertState.PREPARED,
                OutcomeCertainty.NOT_ATTEMPTED,
                None,
                None,
                AttributionKind.NONE,
                Visibility.UNKNOWN,
                None,
                None,
                Count(0),
                None,
                Revision(0),
            )
            intents.prepare_attempt(
                uow, self._projection, attempt, RevisionGuard(job.revision)
            )
        with self._owner.session.transaction() as uow:
            self._active(uow, job)
            marker = intents.mark_dispatch(
                uow,
                self._projection,
                attempt.attempt_id,
                attempt.claim_id,
                _now(),
                RevisionGuard(attempt.revision),
            )
            if marker.disposition == "replayed":
                # Replay is only an observation, never a new remote effect.
                return "recovery"
            attempt = _get(
                uow,
                self._projection,
                "insert_attempts",
                (("attempt_id", attempt.attempt_id),),
            )
        try:
            result = self._target.insert(
                raw,
                thread_id=attempt.requested_target_thread_id,
                date_header=facts.date_policy is DatePolicy.VALID_DATE_HEADER,
            )
        except ProviderFailure as error:
            unknown = error.code is ErrorCode.NETWORK_UNAVAILABLE or (
                error.code is ErrorCode.INVALID_INPUT and error.status is None
            )
            self._result(
                attempt,
                InsertState.PENDING_RECOVERY
                if unknown
                else InsertState.DEFINITE_NOT_INSERTED,
                OutcomeCertainty.UNKNOWN
                if unknown
                else OutcomeCertainty.DEFINITELY_NOT_INSERTED,
                ErrorCode.INSERT_RESULT_UNKNOWN if unknown else error.code,
            )
            if not unknown:
                self._defer(job, error.code, error.retry_after_seconds)
            return "recovery" if unknown else "deferred"
        except Exception:
            self._result(
                attempt,
                InsertState.PENDING_RECOVERY,
                OutcomeCertainty.UNKNOWN,
                ErrorCode.INSERT_RESULT_UNKNOWN,
            )
            return "recovery"
        finally:
            del raw
        attempt = self._result(
            attempt,
            InsertState.KNOWN_INSERTED,
            OutcomeCertainty.INSERTED,
            None,
            target_message_id=result.message_id,
            target_thread_id=result.thread_id,
            attribution=AttributionKind.DIRECT_RESPONSE,
        )
        try:
            readback = self._target.readback(result.message_id)
            if len(readback.raw) > self._max_raw_bytes:
                raise ValueError("invalid_input")
            target_facts = inspect(readback.raw)
            valid = (
                readback.message_id == result.message_id
                and readback.thread_id == result.thread_id
                and (
                    attempt.requested_target_thread_id is None
                    or readback.thread_id == attempt.requested_target_thread_id
                )
                and facts.semantic_version == target_facts.semantic_version
                and facts.semantic_digest == target_facts.semantic_digest
            )
            visibility = (
                Visibility.TRASH
                if "TRASH" in readback.labels
                else Visibility.SPAM
                if "SPAM" in readback.labels
                else Visibility.NORMAL
            )
            del readback
        except ProviderFailure as error:
            attention_code = error.code
            if attention_code not in {
                ErrorCode.INVALID_INPUT,
                ErrorCode.TARGET_AUTH_REQUIRED,
                ErrorCode.TARGET_RATE_LIMITED,
                ErrorCode.NETWORK_UNAVAILABLE,
                ErrorCode.TARGET_STORAGE_FULL,
            }:
                attention_code = ErrorCode.INSERT_RESULT_UNKNOWN
            self._result(
                attempt,
                InsertState.NEEDS_ATTENTION,
                OutcomeCertainty.INSERTED,
                attention_code,
            )
            return "deferred"
        except ValueError:
            valid, visibility = False, Visibility.UNKNOWN
        if not valid or visibility is not Visibility.NORMAL:
            self._result(
                attempt,
                InsertState.NEEDS_ATTENTION,
                OutcomeCertainty.INSERTED,
                ErrorCode.FIDELITY_MISMATCH,
            )
            return "deferred"
        attempt = self._result(
            attempt,
            InsertState.KNOWN_INSERTED,
            OutcomeCertainty.INSERTED,
            None,
            semantic_digest=facts.semantic_digest,
            semantic_version=facts.semantic_version,
            visibility=visibility,
        )
        verified = _now()
        with self._owner.session.transaction() as uow:
            target = _get(
                uow,
                self._projection,
                "thread_targets",
                (
                    ("source_thread_id", attempt.source_thread_id),
                    ("target_thread_id", attempt.target_thread_id),
                ),
            )
            target = target or ThreadTargetRow(
                self._projection,
                attempt.source_thread_id,
                attempt.target_thread_id,
                anchor is None,
                attempt.attempt_id,
                verified,
            )
            mappings.verify_mapping(
                uow,
                self._projection,
                attempt.attempt_id,
                MessageMappingRow(
                    self._projection,
                    attempt.source_message_id,
                    attempt.source_thread_id,
                    Revision(1),
                    attempt.attempt_id,
                    attempt.target_message_id,
                    attempt.target_thread_id,
                    verified,
                    visibility,
                    None,
                    None,
                ),
                MappingHistoryRow(
                    self._projection,
                    attempt.source_message_id,
                    Revision(1),
                    attempt.source_thread_id,
                    attempt.attempt_id,
                    attempt.target_message_id,
                    attempt.target_thread_id,
                    verified,
                    None,
                ),
                TargetOwnershipRow(
                    self._projection,
                    attempt.target_message_id,
                    attempt.source_message_id,
                    attempt.attempt_id,
                    verified,
                ),
                target,
                RevisionGuard(attempt.revision),
            )
        return "verified"

    def _active(self, uow, job):
        thread = _get(
            uow,
            self._projection,
            "tracked_threads",
            (("source_thread_id", job.subject.source_thread_id),),
        )
        if (
            thread is None
            or not thread.active
            or thread.generation != job.subject.generation
        ):
            raise StorageFailure(ErrorCode.GENERATION_STALE)

    def _result(self, attempt, state, certainty, error, **facts):
        now = _now()
        row = replace(
            attempt,
            state=state,
            certainty=certainty,
            error_code=error,
            result_at=attempt.result_at or now,
            revision=next_revision(attempt.revision),
            **facts,
        )
        with self._owner.session.transaction() as uow:
            intents.record_attempt_result(
                uow, self._projection, row, now, RevisionGuard(attempt.revision)
            )
        return row


__all__ = ("ProjectionWorker", "WorkerReceipt")
