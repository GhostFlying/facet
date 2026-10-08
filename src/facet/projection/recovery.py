"""Bounded unknown-insert evidence checks, never insertion or candidate claiming."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from facet.contracts import (
    Claim,
    ClaimPhase,
    ErrorCode,
    LocalId,
    ProviderId,
    Revision,
    Role,
    Timestamp,
)
from facet.db.codecs import timestamp_to_sql
from facet.db.models import RevisionGuard
from facet.db.repositories import intents, jobs, reads
from facet.db.repositories.base import _decode, _query
from facet.db.repositories.serialization import COLUMNS
from facet.gmail.retry import ProviderFailure, blocks_sync
from facet.projection.fidelity import inspect


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryEvidence:
    result: str
    code: ErrorCode
    candidate_count: int = 0
    reason: str | None = None
    target_message_id: ProviderId | None = None
    target_thread_id: ProviderId | None = None


def check_unknown(source, target, attempt, *, max_raw_bytes=35_000_000):
    """Read facts in bounded RAM; a unique match is not an ownership assertion."""
    if attempt.rfc_message_id is None:
        return RecoveryEvidence(
            "attention", ErrorCode.ATTRIBUTION_UNKNOWN, reason="missing_rfc_message_id"
        )
    candidates = target.find_by_rfc_message_id(attempt.rfc_message_id)
    if not candidates:
        return RecoveryEvidence("not_found", ErrorCode.INSERT_RESULT_UNKNOWN)
    if len(candidates) != 1:
        return RecoveryEvidence(
            "duplicate_candidates", ErrorCode.DUPLICATE_CANDIDATES, len(candidates)
        )
    try:
        raw = source.raw(
            attempt.source_message_id,
            thread_id=attempt.source_thread_id,
            max_bytes=max_raw_bytes,
        )
    except ProviderFailure as error:
        if error.role is Role.SOURCE and error.status == 404:
            return RecoveryEvidence(
                "attention", ErrorCode.SOURCE_MISSING, 1, "source_missing"
            )
        raise
    try:
        if len(raw) > max_raw_bytes:
            return RecoveryEvidence(
                "attention", ErrorCode.INVALID_INPUT, 1, "raw_limit"
            )
        source_facts = inspect(raw)
    finally:
        del raw
    if source_facts.raw_digest != attempt.raw_digest:
        return RecoveryEvidence(
            "attention", ErrorCode.FIDELITY_MISMATCH, 1, "source_changed"
        )
    readback = target.readback(candidates[0])
    try:
        if len(readback.raw) > max_raw_bytes:
            return RecoveryEvidence(
                "attention", ErrorCode.INVALID_INPUT, 1, "raw_limit"
            )
        if (
            readback.message_id != candidates[0]
            or attempt.requested_target_thread_id is not None
            and readback.thread_id != attempt.requested_target_thread_id
        ):
            return RecoveryEvidence(
                "attention", ErrorCode.ATTRIBUTION_UNKNOWN, 1, "attribution_unknown"
            )
        # External outbound is explicitly not an automatically claimable copy.
        if {"SENT", "DRAFT"}.intersection(readback.labels):
            return RecoveryEvidence(
                "attention",
                ErrorCode.ATTRIBUTION_UNKNOWN,
                1,
                "external_outbound_candidate",
            )
        facts = inspect(readback.raw)
        if (
            source_facts.semantic_version != facts.semantic_version
            or source_facts.semantic_digest != facts.semantic_digest
            or {"SPAM", "TRASH"}.intersection(readback.labels)
        ):
            return RecoveryEvidence(
                "attention", ErrorCode.FIDELITY_MISMATCH, 1, "fidelity_mismatch"
            )
        return RecoveryEvidence(
            "unique_match",
            ErrorCode.ATTRIBUTION_UNKNOWN,
            1,
            target_message_id=readback.message_id,
            target_thread_id=readback.thread_id,
        )
    finally:
        del readback


class UnknownInsertChecks:
    def __init__(self, owner, source, target, *, max_raw_bytes=35_000_000):
        if type(max_raw_bytes) is not int or not 1 <= max_raw_bytes <= 35_000_000:
            raise ValueError("invalid_input")
        self.owner, self.source, self.target = owner, source, target
        self.max_raw_bytes = max_raw_bytes

    def run(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid_input")
        projection = self.owner.projection_id
        now = Timestamp(datetime.now(UTC))
        with self.owner.session.transaction() as uow:
            rows = _query(
                uow,
                "SELECT "
                + ",".join("j." + c for c in COLUMNS["sync_jobs"])
                + " FROM sync_jobs j JOIN insert_attempts a "
                "ON a.projection_id=j.projection_id "
                "AND a.attempt_id=j.attempt_id WHERE j.projection_id=? "
                "AND j.kind='recover_insert' AND j.state IN('queued','retry_wait') "
                "AND a.state='pending_recovery' AND (j.next_attempt_at IS NULL OR "
                "j.next_attempt_at<=?) AND (a.next_recovery_at IS NULL OR "
                "a.next_recovery_at<=?) ORDER BY j.created_at,j.job_id LIMIT ?",
                (projection.value, timestamp_to_sql(now), timestamp_to_sql(now), limit),
                maximum=limit,
            )
            selected = tuple(_decode(uow, projection, "sync_jobs", row) for row in rows)
        checked = 0
        for job in selected:
            now = Timestamp(datetime.now(UTC))
            with self.owner.session.transaction() as uow:
                attempt = reads.get_attempt(uow, projection, job.subject.attempt_id)
                claim = Claim(
                    LocalId(uuid4().hex),
                    self.owner.owner_info.owner_run_id,
                    now,
                    attempt.generation,
                    Revision(job.revision.value + 1),
                    ClaimPhase.PREPARING,
                )
                jobs.claim(
                    uow, projection, job.job_id, claim, RevisionGuard(job.revision), now
                )
            failure = None
            try:
                evidence = check_unknown(
                    self.source, self.target, attempt, max_raw_bytes=self.max_raw_bytes
                )
                code = evidence.code
                # Content equality cannot establish provenance. Keep checking
                # an empty index; real ambiguity is precise retained attention.
                retry = evidence.result == "not_found"
            except ProviderFailure as error:
                code, failure = error.code, error
                if error.role is Role.SOURCE and error.status == 404:
                    code = ErrorCode.SOURCE_MISSING
                retry = blocks_sync(error) or code in {
                    ErrorCode.SOURCE_AUTH_REQUIRED,
                    ErrorCode.TARGET_AUTH_REQUIRED,
                    ErrorCode.SOURCE_RATE_LIMITED,
                    ErrorCode.TARGET_RATE_LIMITED,
                    ErrorCode.NETWORK_UNAVAILABLE,
                    ErrorCode.TARGET_STORAGE_FULL,
                }
            now = Timestamp(datetime.now(UTC))
            delay = min(3600, 30 * 2 ** min(attempt.recovery_checks.value, 7))
            if failure is not None:
                delay = max(delay, failure.retry_after_seconds or 0)
            with self.owner.session.transaction() as uow:
                intents.record_recovery_check(
                    uow,
                    projection,
                    attempt.attempt_id,
                    code,
                    now,
                    Timestamp(now.value + timedelta(seconds=delay)) if retry else None,
                    RevisionGuard(attempt.revision),
                )
            checked += 1
            if failure is not None and blocks_sync(failure):
                raise failure
        return checked
