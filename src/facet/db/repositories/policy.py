"""Policy metadata transactions, not sender/authenticity or disclosure decisions."""

from dataclasses import replace
from typing import get_args

from facet.contracts import (
    ErrorCode,
    Generation,
    Revision,
    RuleKind,
    ThreadGenerationGuard,
)
from facet.contracts.records import AdmissionRef as Admissions

from ..codecs import (
    MAX_INTEGER,
    AuditKind,
    AuditObjectKind,
    StorageFailure,
    ThreadStopReason,
    next_revision,
    timestamp_to_sql,
)
from ..models import (
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    SyncJobRow,
    WriteReceipt,
)
from .audit import _audit
from .base import (
    _batch,
    _conflict,
    _get,
    _guard,
    _insert,
    _mutating,
    _query,
    _require_row,
)


@_mutating
def publish_rules(uow, projection_id, rules, revisions, snapshot, members, guard):
    _batch(rules, RuleRow)
    _batch(revisions, RuleRevisionRow)
    _batch(members, RulesetMemberRow)
    _require_row(projection_id, "rulesets", snapshot)
    projection = _get(uow, projection_id, "projections", ())
    if projection is None:
        _conflict()
    _guard(projection.ruleset_revision, guard)
    if (
        snapshot.revision != next_revision(projection.ruleset_revision)
        or not snapshot.sealed
    ):
        _conflict()
    for row in rules:
        _require_row(projection_id, "rules", row)
        old = _get(uow, projection_id, "rules", (("rule_id", row.rule_id),))
        if old is None:
            _insert(uow, projection_id, "rules", row)
        elif (old.kind, old.normalized_value) != (row.kind, row.normalized_value):
            _conflict()
        else:
            if row.current_revision != next_revision(old.current_revision):
                _conflict()
            uow._execute(
                "UPDATE rules SET current_revision=? WHERE projection_id=? AND "
                "rule_id=?",
                (row.current_revision.value, projection_id.value, row.rule_id.value),
            )
    for row in revisions:
        _insert(uow, projection_id, "rule_revisions", row)
    _insert(uow, projection_id, "rulesets", replace(snapshot, sealed=False))
    for row in members:
        if row.ruleset_revision != snapshot.revision:
            _conflict()
        _insert(uow, projection_id, "ruleset_members", row)
    uow._execute(
        "UPDATE rulesets SET sealed=1 WHERE projection_id=? AND revision=?",
        (projection_id.value, snapshot.revision.value),
    )
    uow._execute(
        "UPDATE projections SET ruleset_revision=? WHERE projection_id=?",
        (snapshot.revision.value, projection_id.value),
    )
    for row in revisions:
        _audit(
            uow,
            projection_id,
            AuditKind.RULE_CHANGED,
            AuditObjectKind.RULE,
            snapshot.created_at,
            local_id=row.rule_id,
            after_revision=row.revision,
        )
    return WriteReceipt("created", projection_id, snapshot.revision)


def _validate_admission(uow, projection_id, thread, admission):
    ref = admission.admission
    if type(ref) not in get_args(Admissions):
        _conflict()
    if ref.tag == "manual_thread":
        # A UUID is not a preview/authorization registry entry.
        raise StorageFailure(ErrorCode.OWNER_UNAVAILABLE)
    if ref.tag in {"future_rule", "initial_backfill"}:
        rule = _get(
            uow,
            projection_id,
            "rule_revisions",
            (("rule_id", ref.rule.rule_id), ("revision", ref.rule.revision)),
        )
        if (
            rule is None
            or not rule.enabled
            or rule.policy_version != ref.policy_version
            or rule.effective_at.value > thread.admitted_at.value
        ):
            _conflict()
        identity = _get(uow, projection_id, "rules", (("rule_id", ref.rule.rule_id),))
        if identity is None or identity.kind not in {
            RuleKind.ALLOW_SENDER,
            RuleKind.ALLOW_DOMAIN,
        }:
            _conflict()
        if ref.tag == "initial_backfill":
            epoch = _get(uow, projection_id, "epochs", (("epoch_id", ref.epoch_id),))
            if epoch is None or epoch.decision.tag != "backfill_start":
                _conflict()
            member = _get(
                uow,
                projection_id,
                "ruleset_members",
                (
                    ("ruleset_revision", epoch.decision.ruleset_revision),
                    ("rule_id", ref.rule.rule_id),
                ),
            )
            if member is None or member.rule_revision != ref.rule.revision:
                _conflict()
    if ref.tag == "action_label":
        action = _get(
            uow,
            projection_id,
            "action_commands",
            (("action_command_id", ref.action_command_id),),
        )
        if (
            action is None
            or action.source_thread_id != thread.source_thread_id
            or action.kind.value == "blacklist"
        ):
            _conflict()


@_mutating
def admit_thread(uow, projection_id, thread, admission, jobs, guard):
    _require_row(projection_id, "tracked_threads", thread)
    _require_row(projection_id, "thread_admissions", admission)
    _batch(jobs, SyncJobRow)
    if type(guard) not in get_args(ThreadGenerationGuard):
        _conflict()
    if (
        not thread.active
        or thread.generation.value < 1
        or (
            admission.source_thread_id != thread.source_thread_id
            or admission.generation != thread.generation
            or admission.admission_revision != thread.admission_revision
            or admission.admitted_at != thread.admitted_at
        )
    ):
        _conflict()
    old = _get(
        uow,
        projection_id,
        "tracked_threads",
        (("source_thread_id", thread.source_thread_id),),
    )
    _validate_admission(uow, projection_id, thread, admission)
    if old is None:
        if (
            guard.tag != "untracked"
            or thread.generation.value != 1
            or thread.admission_revision.value != 1
        ):
            _conflict()
        _insert(uow, projection_id, "tracked_threads", thread)
        disposition = "created"
    else:
        if guard.tag != "tracked" or guard.generation != old.generation:
            raise StorageFailure(ErrorCode.GENERATION_STALE)
        if old.active:
            previous = _get(
                uow,
                projection_id,
                "thread_admissions",
                (
                    ("source_thread_id", old.source_thread_id),
                    ("admission_revision", old.admission_revision),
                ),
            )
            if old != thread or previous != admission:
                _conflict()
            from .jobs import enqueue

            for job in jobs:
                enqueue(uow, projection_id, job)
            return WriteReceipt(
                "replayed", old.source_thread_id, old.admission_revision
            )
        if thread.generation.value != next_revision(
            Revision(old.generation.value)
        ).value or thread.admission_revision != next_revision(old.admission_revision):
            _conflict()
        uow._execute(
            "UPDATE tracked_threads SET "
            "active=1,generation=?,admitted_at=?,stopped_at=NULL,"
            "stop_reason=NULL,admission_revision=? "
            "WHERE projection_id=? AND source_thread_id=?",
            (
                thread.generation.value,
                timestamp_to_sql(thread.admitted_at),
                thread.admission_revision.value,
                projection_id.value,
                thread.source_thread_id.value,
            ),
        )
        disposition = "updated"
    _insert(uow, projection_id, "thread_admissions", admission)
    from .jobs import enqueue

    for job in jobs:
        enqueue(uow, projection_id, job)
    _audit(
        uow,
        projection_id,
        AuditKind.THREAD_ADMITTED,
        AuditObjectKind.THREAD,
        thread.admitted_at,
        thread_id=thread.source_thread_id,
        before_revision=None if old is None else old.admission_revision,
        after_revision=thread.admission_revision,
    )
    return WriteReceipt(disposition, thread.source_thread_id, thread.admission_revision)


_STOP_TARGETS = (
    "SELECT j.job_id FROM sync_jobs j WHERE j.projection_id=? "
    "AND j.source_thread_id=? AND j.generation=? "
    "AND j.state IN('queued','retry_wait','blocked','claimed') "
    "AND NOT EXISTS(SELECT 1 FROM insert_attempts a "
    "WHERE a.projection_id=j.projection_id AND a.job_id=j.job_id "
    "AND a.state IN('dispatch_started','pending_recovery',"
    "'known_inserted','needs_attention'))"
)


@_mutating
def stop_thread(uow, projection_id, thread_id, expected_generation, stopped_at, reason):
    if (
        type(expected_generation) is not Generation
        or type(reason) is not ThreadStopReason
    ):
        _conflict()
    thread = _get(
        uow, projection_id, "tracked_threads", (("source_thread_id", thread_id),)
    )
    if thread is None or not thread.active or thread.generation != expected_generation:
        raise StorageFailure(ErrorCode.GENERATION_STALE)
    new_generation = next_revision(Revision(thread.generation.value))
    timestamp = timestamp_to_sql(stopped_at)
    identity = (projection_id.value, thread_id.value, expected_generation.value)
    if _query(
        uow,
        _STOP_TARGETS + " AND j.revision=? LIMIT 1",
        (*identity, MAX_INTEGER),
        maximum=1,
    ) or _query(
        uow,
        "SELECT 1 FROM insert_attempts WHERE projection_id=? "
        "AND source_thread_id=? AND generation=? AND state='prepared' "
        "AND revision=? LIMIT 1",
        (*identity, MAX_INTEGER),
        maximum=1,
    ):
        _conflict()
    uow._execute(
        "UPDATE tracked_threads SET active=0,generation=?,stopped_at=?,stop_reason=? "
        "WHERE projection_id=? AND source_thread_id=?",
        (
            new_generation.value,
            timestamp,
            reason.value,
            projection_id.value,
            thread_id.value,
        ),
    )
    uow._execute(
        "UPDATE insert_attempts SET "
        "state='cancelled_before_dispatch',result_at=?,revision=revision+1 WHERE "
        "projection_id=? AND source_thread_id=? AND generation=? AND "
        "state='prepared'",
        (timestamp, *identity),
    )
    # A factual dispatched/unknown/known effect keeps its job and claim. Other
    # unsent work loses scheduling permission without deleting old facts.
    # Set-based statements avoid truncating a large thread at the read-page cap.
    uow._execute(
        "DELETE FROM job_claims WHERE projection_id=? AND job_id IN("
        + _STOP_TARGETS
        + ")",
        (projection_id.value, *identity),
    )
    uow._execute(
        "UPDATE sync_jobs SET state='cancelled',revision=revision+1,updated_at=?,"
        "next_attempt_at=NULL WHERE projection_id=? AND job_id IN("
        + _STOP_TARGETS
        + ")",
        (timestamp, projection_id.value, *identity),
    )
    _audit(
        uow,
        projection_id,
        AuditKind.THREAD_STOPPED,
        AuditObjectKind.THREAD,
        stopped_at,
        thread_id=thread_id,
        before_revision=Revision(thread.generation.value),
        after_revision=new_generation,
    )
    return WriteReceipt("updated", thread_id, Revision(new_generation.value))
