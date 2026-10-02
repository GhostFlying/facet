"""AP01–12: real WAL/UoW action facts, not production M5 learning authority."""

import sqlite3
from contextlib import contextmanager, suppress
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest
from fakes.privacy import (
    Profile,
    assert_private_boundary,
    inspect_files,
    inspect_sqlite,
    markers,
)
from test_db_epochs import epoch
from test_db_events import event
from test_db_repositories import (
    T,
    admit,
    claim,
    job,
    publish,
    ready_test_metadata,
    thread_rows,
    view,
)
from test_db_repositories import state as state
from test_db_schema import NOW, P, lid

from facet.contracts import (
    ErrorCode,
    Generation,
    JobState,
    LabelChange,
    PolicyVersion,
    ProviderId,
    Revision,
    RuleKind,
    RuleOrigin,
    SourceMode,
    Timestamp,
)
from facet.contracts.records import (
    AdmissionRefActionLabel,
    JobSubjectExpandThread,
    RuleRef,
    ThreadGenerationGuardTracked,
    ThreadGenerationGuardUntracked,
)
from facet.db.codecs import (
    MAX_INTEGER,
    ActionKind,
    ActionState,
    CleanupState,
    EventProcessing,
    RuleValue,
    StorageFailure,
    ThreadStopReason,
)
from facet.db.connection import _attach_writer
from facet.db.keys import event_key
from facet.db.migrations.v0001 import TABLES
from facet.db.models import (
    ActionCommandRow,
    RevisionGuard,
    RuleRevisionRow,
    RuleRow,
    RulesetMemberRow,
    RulesetRow,
    WriteReceipt,
)
from facet.db.repositories import actions, epochs, events, jobs, policy, reads
from facet.db.repositories.base import _get, _insert


class SyntheticActionProducer:
    """Fixed test-only producer, never exported or included in the wheel."""


@pytest.fixture
def producer(monkeypatch):
    assert actions._ACTION_PRODUCER_TYPES == ()
    monkeypatch.setattr(actions, "_ACTION_PRODUCER_TYPES", (SyntheticActionProducer,))
    yield SyntheticActionProducer()
    assert not actions._ENROLLED_SCOPES


def action_row(n=700, *, kind=ActionKind.ADD_SENDER, source=None):
    source = source or replace(
        event(n, thread=T, tag="label_changed"), processing=EventProcessing.RESOLVED
    )
    key = source.event.key
    return ActionCommandRow(
        P,
        lid(n + 1000),
        source.event_id,
        key.history_record_id,
        key.label_id,
        source.event.source_thread_id,
        kind,
        ActionState.PENDING,
        CleanupState.NOT_REQUESTED,
        source.event.observed_at,
        None,
        None,
        Revision(0),
    )


def register(session, n=700, *, kind=ActionKind.ADD_SENDER, source=None):
    source = source or replace(
        event(n, thread=T, tag="label_changed"), processing=EventProcessing.RESOLVED
    )
    row = action_row(n, kind=kind, source=source)
    with session.transaction() as uow:
        _insert(uow, P, "source_events", source)
        receipt = actions.register_action(uow, P, row)
    assert receipt == WriteReceipt("created", row.action_command_id, Revision(0))
    return row


def prepare_epoch(session, *, n=900):
    with session.transaction() as uow:
        current = reads.get_projection(uow, P).ruleset_revision
        value = epoch(n)
        value = replace(
            value, decision=replace(value.decision, ruleset_revision=current)
        )
        epochs.start_epoch(uow, P, value, ())
    return value


def rule_rows(kind=ActionKind.ADD_SENDER, *, n=20, revision=1, snapshot=1, at=NOW):
    rule_kind = {
        ActionKind.ADD_SENDER: RuleKind.ALLOW_SENDER,
        ActionKind.ADD_DOMAIN: RuleKind.ALLOW_DOMAIN,
        ActionKind.BLACKLIST: RuleKind.BLACKLIST_SENDER,
    }[kind]
    value = (
        "example.invalid"
        if kind is ActionKind.ADD_DOMAIN
        else (
            "synthetic@example.invalid"
            if n in {10, 20}
            else f"sender{n}@example.invalid"
        )
    )
    rule = RuleRow(P, lid(n), rule_kind, RuleValue(value), Revision(revision))
    version = RuleRevisionRow(
        P,
        rule.rule_id,
        rule.current_revision,
        True,
        at,
        RuleOrigin.ACTION_LABEL,
        PolicyVersion("synthetic-v1"),
    )
    sealed = RulesetRow(P, Revision(snapshot), at, True)
    member = RulesetMemberRow(P, sealed.revision, rule.rule_id, rule.current_revision)
    return rule, version, sealed, member


def expansion(selected_epoch, *, n=950, generation=1, thread=T):
    return replace(
        job(
            n,
            subject=JobSubjectExpandThread(
                "expand_thread", thread, selected_epoch.epoch_id, Generation(generation)
            ),
        ),
        origin_epoch_id=selected_epoch.epoch_id,
    )


def begin(uow, row, producer, *, rule_id=20, rule_revision=1, work=None):
    selection = actions._ActionSelection(
        row.action_command_id,
        RuleRef(lid(rule_id), Revision(rule_revision)),
        None if row.kind is ActionKind.BLACKLIST else work.job_id,
    )
    actions._begin_action_effect(
        uow, P, selection, RevisionGuard(row.revision), producer
    )
    return uow._action_scope


def effects(uow, row, producer, selected_epoch=None, *, new_rule=True, work=None):
    if work is None and row.kind is not ActionKind.BLACKLIST:
        work = expansion(selected_epoch)
    scope = begin(uow, row, producer, rule_id=20 if new_rule else 10, work=work)
    if new_rule:
        current = reads.get_projection(uow, P).ruleset_revision
        rule, version, sealed, member = rule_rows(row.kind, snapshot=current.value + 1)
        members = (
            (
                replace(
                    _get(
                        uow,
                        P,
                        "ruleset_members",
                        (
                            ("ruleset_revision", current),
                            ("rule_id", lid(10)),
                        ),
                    ),
                    ruleset_revision=sealed.revision,
                ),
            )
            if current.value
            else ()
        )
        policy.publish_rules(
            uow,
            P,
            (rule,),
            (version,),
            sealed,
            (*members, member),
            RevisionGuard(current),
        )
    before = scope.before_thread
    if row.kind is ActionKind.BLACKLIST:
        if before is not None and before.active:
            policy.stop_thread(
                uow, P, T, before.generation, NOW, ThreadStopReason.BLACKLIST
            )
    elif before is None or not before.active:
        generation = 1 if before is None else before.generation.value + 1
        revision = 1 if before is None else before.admission_revision.value + 1
        tracked, admitted = thread_rows(
            generation=generation, admission_revision=revision
        )
        admitted = replace(
            admitted,
            admission=AdmissionRefActionLabel("action_label", row.action_command_id),
        )
        guard = (
            ThreadGenerationGuardUntracked("untracked")
            if before is None
            else (ThreadGenerationGuardTracked("tracked", before.generation))
        )
        policy.admit_thread(uow, P, tracked, admitted, (), guard)
    if work is not None:
        jobs.enqueue(uow, P, work)
    return scope


def executed(row, *, at=NOW):
    return replace(
        row, state=ActionState.EXECUTED, executed_at=at, revision=Revision(1)
    )


def execute(session, row, producer, selected_epoch=None, **kwargs):
    with session.transaction() as uow:
        effects(uow, row, producer, selected_epoch, **kwargs)
        receipt = actions.complete_action(
            uow, P, executed(row), RevisionGuard(row.revision)
        )
        assert reads.get_action(uow, P, row.action_command_id) == executed(row)
    return receipt


def image(connection):
    # Test-only physical relational comparison of the entire fixed schema.
    return {
        table.name: tuple(connection.execute("SELECT * FROM " + table.name).fetchall())
        for table in TABLES
    }


@contextmanager
def reopen(state):
    path, _, session, info = state
    session.close()
    connection = sqlite3.connect(path, autocommit=True)
    actual = _attach_writer(connection, info)
    try:
        yield path, connection, actual, info
    finally:
        actual.close()


def get_action(state, row):
    # Each call is actual isolated snapshot read qualification, not a parent
    # proxy pretending to be a production read bridge.
    with view(state) as reader:
        return reader.get_action(P, row.action_command_id)


def test_ap01_registration_alias_retains_first_provenance_and_reactivation(state):
    _, connection, session, _ = state
    first = register(session)
    second_event = replace(
        event(701, thread=T, tag="label_changed"), processing=EventProcessing.CONSUMED
    )
    key = replace(second_event.event.key, history_record_id=first.history_record_id)
    observed = Timestamp(NOW.value + timedelta(seconds=2))
    second_event = replace(
        second_event,
        event_key=event_key(P, key),
        event=replace(second_event.event, key=key, observed_at=observed),
    )
    alias = action_row(701, source=second_event)
    with session.transaction() as uow:
        _insert(uow, P, "source_events", second_event)
        before = connection.total_changes
        assert actions.register_action(uow, P, alias) == WriteReceipt(
            "replayed", first.action_command_id, Revision(0)
        )
        assert connection.total_changes == before
    assert get_action(state, first) == first
    assert get_action(state, alias) is None
    next_activation = register(session, 702)
    assert next_activation.history_record_id != first.history_record_id
    assert connection.execute("SELECT COUNT(*) FROM action_commands").fetchone() == (2,)


@pytest.mark.parametrize(
    "bad",
    [
        "pending",
        "attention",
        "unresolved",
        "removed",
        "snapshot",
        "wrong_history",
        "wrong_label",
        "wrong_thread",
        "wrong_time",
        "wrong_state",
        "wrong_revision",
        "wrong_cleanup",
        "wrong_error",
        "wrong_execution",
        "missing_event",
    ],
)
def test_ap01_invalid_event_or_registration_rolls_back(state, bad):
    _, connection, session, _ = state
    source = replace(
        event(700, thread=T, tag="label_changed"), processing=EventProcessing.RESOLVED
    )
    row = action_row(source=source)
    if bad in {"pending", "attention"}:
        source = replace(
            source,
            processing=(
                EventProcessing.PENDING
                if bad == "pending"
                else EventProcessing.NEEDS_ATTENTION
            ),
        )
    elif bad == "unresolved":
        source = replace(source, event=replace(source.event, source_thread_id=None))
    elif bad == "removed":
        key = replace(source.event.key, change=LabelChange.REMOVED)
        source = replace(
            source, event_key=event_key(P, key), event=replace(source.event, key=key)
        )
    elif bad == "snapshot":
        source = replace(event(700, thread=T), processing=EventProcessing.RESOLVED)
    else:
        changes = {
            "wrong_history": {"history_record_id": ProviderId("other-history")},
            "wrong_label": {"label_id": ProviderId("other-label")},
            "wrong_thread": {"source_thread_id": ProviderId("other-thread")},
            "wrong_time": {"observed_at": Timestamp(NOW.value + timedelta(seconds=1))},
            "wrong_state": {"state": ActionState.NEEDS_ATTENTION},
            "wrong_revision": {"revision": Revision(1)},
            "wrong_cleanup": {"cleanup": CleanupState.QUEUED},
            "wrong_error": {"error_code": ErrorCode.SOURCE_AUTH_REQUIRED},
            "wrong_execution": {"executed_at": NOW},
            "missing_event": {"event_id": lid(999)},
        }
        row = replace(row, **changes[bad])
    before = image(connection)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        _insert(uow, P, "source_events", source)
        actions.register_action(uow, P, row)
    assert image(connection) == before


@pytest.mark.parametrize("collision", ["kind", "id"])
def test_ap01_conflicting_kind_or_alias_id_refuses(state, collision):
    _, _, session, _ = state
    original = register(session)
    other = register(session, 701)
    incoming = (
        replace(original, kind=ActionKind.BLACKLIST)
        if collision == "kind"
        else (replace(original, action_command_id=other.action_command_id))
    )
    with pytest.raises(StorageFailure), session.transaction() as uow:
        actions.register_action(uow, P, incoming)
    assert get_action(state, original) == original


def test_ap03_production_registry_and_forged_scope_cannot_complete(state):
    _, _, session, _ = state
    row = register(session)
    assert actions._ACTION_PRODUCER_TYPES == ()
    selection = actions._ActionSelection(
        row.action_command_id, RuleRef(lid(20), Revision(1)), lid(950)
    )
    with (
        pytest.raises(StorageFailure, match="owner_unavailable"),
        session.transaction() as uow,
    ):
        actions._begin_action_effect(
            uow, P, selection, RevisionGuard(row.revision), object()
        )
    with (
        pytest.raises(StorageFailure, match="owner_unavailable"),
        session.transaction() as uow,
    ):
        actions.complete_action(uow, P, executed(row), RevisionGuard(row.revision))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        uow._action_scope = object.__new__(actions._ActionScope)
        actions.complete_action(uow, P, executed(row), RevisionGuard(row.revision))
    assert get_action(state, row) == row


@pytest.mark.parametrize("kind", list(ActionKind))
def test_ap04_all_kinds_commit_real_effect_groups_after_reopen(state, producer, kind):
    _, connection, session, _ = state
    row = register(session, kind=kind)
    selected_epoch = None if kind is ActionKind.BLACKLIST else prepare_epoch(session)
    assert execute(session, row, producer, selected_epoch) == WriteReceipt(
        "updated", row.action_command_id, Revision(1)
    )
    expected = image(connection)
    with reopen(state) as actual:
        assert image(actual[1]) == expected
        assert get_action(actual, row) == executed(row)
        with view(actual) as reader:
            assert (
                reader.get_rule(P, lid(20)).kind
                is {
                    ActionKind.ADD_SENDER: RuleKind.ALLOW_SENDER,
                    ActionKind.ADD_DOMAIN: RuleKind.ALLOW_DOMAIN,
                    ActionKind.BLACKLIST: RuleKind.BLACKLIST_SENDER,
                }[kind]
            )
            tracked = reader.get_thread(P, T)
            if kind is ActionKind.BLACKLIST:
                assert tracked is None
            else:
                assert tracked.active and tracked.generation == Generation(1)
                assert reader.get_job(P, lid(950)).subject.source_thread_id == T
        if kind is not ActionKind.BLACKLIST:
            assert actual[1].execute(
                "SELECT action_command_id FROM thread_admissions"
            ).fetchone() == (row.action_command_id.value,)
            assert actual[1].execute(
                "SELECT epoch_id,job_id FROM epoch_jobs"
            ).fetchone() == (
                selected_epoch.epoch_id.value,
                lid(950).value,
            )


def test_ap05_enabled_rule_active_thread_and_job_alias_keep_original_facts(
    state, producer
):
    _, connection, session, _ = state
    publish(session)
    original_thread, original_admission = admit(session)
    selected_epoch = prepare_epoch(session)
    original_job = expansion(selected_epoch, n=951)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, original_job)
    row = register(session)
    rule_before = connection.execute("SELECT * FROM rule_revisions").fetchall()
    alias = replace(original_job, job_id=lid(950))
    execute(session, row, producer, selected_epoch, new_rule=False, work=alias)
    assert connection.execute("SELECT * FROM rule_revisions").fetchall() == rule_before
    assert connection.execute(
        "SELECT ruleset_revision FROM projections"
    ).fetchone() == (1,)
    with view(state) as reader:
        assert reader.get_thread(P, T) == original_thread
        assert reader.get_job(P, lid(951)) == original_job
        assert reader.get_job(P, lid(950)) is None
    with session.transaction() as uow:
        assert (
            _get(
                uow,
                P,
                "thread_admissions",
                (
                    ("source_thread_id", T),
                    ("admission_revision", Revision(1)),
                ),
            )
            == original_admission
        )


@pytest.mark.parametrize("kind", list(ActionKind))
@pytest.mark.parametrize("caught", [False, True])
def test_ap05_enabled_current_member_next_revision_cannot_replace_provenance(
    state, producer, kind, caught
):
    _, connection, session, _ = state
    initial, version, sealed, member = rule_rows(kind, n=10)
    version = replace(version, origin=RuleOrigin.CLI)
    with session.transaction() as uow:
        policy.publish_rules(
            uow,
            P,
            (initial,),
            (version,),
            sealed,
            (member,),
            RevisionGuard(Revision(0)),
        )
    if kind is not ActionKind.BLACKLIST:
        admit(session)
    row = register(session, kind=kind)
    selected_epoch = None if kind is ActionKind.BLACKLIST else prepare_epoch(session)
    work = None if selected_epoch is None else expansion(selected_epoch)
    later = Timestamp(NOW.value + timedelta(seconds=10))
    before = image(connection)

    def republish(uow):
        begin(uow, row, producer, rule_id=10, rule_revision=2, work=work)
        if work is not None:
            # Real preceding SQL must disappear even if the refusal is caught.
            jobs.enqueue(uow, P, work)
        rule, revision, snapshot, selected = rule_rows(
            kind, n=10, revision=2, snapshot=2, at=later
        )
        policy.publish_rules(
            uow,
            P,
            (rule,),
            (revision,),
            snapshot,
            (selected,),
            RevisionGuard(Revision(1)),
        )
        actions.complete_action(
            uow, P, executed(row, at=later), RevisionGuard(row.revision)
        )

    with pytest.raises(StorageFailure) as failure, session.transaction() as uow:
        if caught:
            with suppress(StorageFailure):
                republish(uow)
        else:
            republish(uow)
    assert failure.value.args == (ErrorCode.CONSISTENCY_FAILURE.value,)
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == row
        with view(actual) as reader:
            assert reader.get_rule(P, lid(10)) == initial
            assert reader.get_projection(P).ruleset_revision == Revision(1)


@pytest.mark.parametrize("kind", list(ActionKind))
@pytest.mark.parametrize(
    "prior", ["preserved", "absent", "disabled", "out_of_snapshot"]
)
def test_ap05_preserved_rule_or_legitimate_selected_publication_commits(
    state, producer, kind, prior
):
    _, connection, session, _ = state
    if prior != "absent":
        initial, version, sealed, member = rule_rows(kind, n=10)
        version = replace(version, enabled=prior != "disabled", origin=RuleOrigin.CLI)
        with session.transaction() as uow:
            policy.publish_rules(
                uow,
                P,
                (initial,),
                (version,),
                sealed,
                () if prior == "out_of_snapshot" else (member,),
                RevisionGuard(Revision(0)),
            )
    row = register(session, kind=kind)
    selected_epoch = None if kind is ActionKind.BLACKLIST else prepare_epoch(session)
    work = None if selected_epoch is None else expansion(selected_epoch)
    later = Timestamp(NOW.value + timedelta(seconds=10))
    revision_number = 1 if prior in {"preserved", "absent"} else 2
    expected_snapshot = 1 if prior in {"preserved", "absent"} else 2
    prior_rules = tuple(connection.execute("SELECT * FROM rule_revisions").fetchall())
    with session.transaction() as uow:
        begin(uow, row, producer, rule_id=10, rule_revision=revision_number, work=work)
        if prior != "preserved":
            rule, version, sealed, member = rule_rows(
                kind,
                n=10,
                revision=revision_number,
                snapshot=expected_snapshot,
                at=later,
            )
            policy.publish_rules(
                uow,
                P,
                (rule,),
                (version,),
                sealed,
                (member,),
                RevisionGuard(Revision(0 if prior == "absent" else 1)),
            )
        if work is not None:
            tracked, admission = thread_rows()
            tracked = replace(tracked, admitted_at=later)
            admission = replace(
                admission,
                admitted_at=later,
                admission=AdmissionRefActionLabel(
                    "action_label", row.action_command_id
                ),
            )
            policy.admit_thread(
                uow,
                P,
                tracked,
                admission,
                (),
                ThreadGenerationGuardUntracked("untracked"),
            )
            jobs.enqueue(uow, P, work)
        actions.complete_action(
            uow, P, executed(row, at=later), RevisionGuard(row.revision)
        )
    with reopen(state) as actual:
        assert get_action(actual, row) == executed(row, at=later)
        with view(actual) as reader:
            assert reader.get_rule(P, lid(10)).current_revision == Revision(
                revision_number
            )
            assert reader.get_projection(P).ruleset_revision == Revision(
                expected_snapshot
            )
        stored_versions = tuple(
            actual[1].execute("SELECT * FROM rule_revisions").fetchall()
        )
        if prior == "preserved":
            assert stored_versions == prior_rules
        else:
            assert len(stored_versions) == len(prior_rules) + 1
            assert actual[1].execute(
                "SELECT origin,effective_at FROM rule_revisions WHERE revision=?",
                (revision_number,),
            ).fetchone() == ("action_label", int(later.value.timestamp() * 1_000_000))


@pytest.mark.parametrize(
    "stage",
    [
        "rule",
        "revision",
        "snapshot",
        "member",
        "thread",
        "admission",
        "job",
        "link",
        "marker",
    ],
)
@pytest.mark.parametrize("caught", [False, True])
def test_ap08_after_sql_abort_rolls_back_all_rows_and_reopens(
    state, producer, stage, caught
):
    _, connection, session, _ = state
    row = register(session)
    selected_epoch = prepare_epoch(session)
    table, verb = {
        "rule": ("rules", "INSERT"),
        "revision": ("rule_revisions", "INSERT"),
        "snapshot": ("rulesets", "INSERT"),
        "member": ("ruleset_members", "INSERT"),
        "thread": ("tracked_threads", "INSERT"),
        "admission": ("thread_admissions", "INSERT"),
        "job": ("sync_jobs", "INSERT"),
        "link": ("epoch_jobs", "INSERT"),
        "marker": ("action_commands", "UPDATE"),
    }[stage]
    connection.execute(
        f"CREATE TEMP TRIGGER fail_action AFTER {verb} ON {table} "
        "BEGIN SELECT RAISE(ABORT,'synthetic-action-failure'); END"
    )
    before = image(connection)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        if caught:
            with suppress(StorageFailure):
                effects(uow, row, producer, selected_epoch)
                actions.complete_action(
                    uow, P, executed(row), RevisionGuard(row.revision)
                )
        else:
            effects(uow, row, producer, selected_epoch)
            actions.complete_action(uow, P, executed(row), RevisionGuard(row.revision))
    assert not actions._ENROLLED_SCOPES
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == row


@pytest.mark.parametrize(
    "later",
    [
        "stop",
        "enqueue",
        "begin",
        "cleanup",
        "complete",
        "claim",
        "replay_admit",
        "publish",
        "epoch",
    ],
)
def test_ap08_consumed_scope_blocks_every_later_mutator_even_caught(
    state, producer, later
):
    _, connection, session, info = state
    row = register(session)
    selected_epoch = prepare_epoch(session)
    before = image(connection)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        effects(uow, row, producer, selected_epoch)
        actions.complete_action(uow, P, executed(row), RevisionGuard(row.revision))
        changes = connection.total_changes
        with pytest.raises(StorageFailure):
            if later == "stop":
                policy.stop_thread(
                    uow, P, T, Generation(1), NOW, ThreadStopReason.MANUAL_STOP
                )
            elif later == "enqueue":
                jobs.enqueue(uow, P, expansion(selected_epoch))
            elif later == "begin":
                begin(uow, row, producer, work=expansion(selected_epoch))
            elif later == "cleanup":
                actions.record_cleanup(
                    uow,
                    P,
                    row.action_command_id,
                    CleanupState.NOT_REQUESTED,
                    None,
                    RevisionGuard(Revision(1)),
                )
            elif later == "complete":
                actions.complete_action(
                    uow, P, executed(row), RevisionGuard(Revision(1))
                )
            elif later == "claim":
                jobs.claim(uow, P, lid(950), None, RevisionGuard(Revision(0)), NOW)
            elif later == "replay_admit":
                tracked = reads.get_thread(uow, P, T)
                admitted = _get(
                    uow,
                    P,
                    "thread_admissions",
                    (("source_thread_id", T), ("admission_revision", Revision(1))),
                )
                policy.admit_thread(
                    uow,
                    P,
                    tracked,
                    admitted,
                    (),
                    ThreadGenerationGuardTracked("tracked", Generation(1)),
                )
            elif later == "publish":
                policy.publish_rules(
                    uow,
                    P,
                    (),
                    (),
                    RulesetRow(P, Revision(2), NOW, True),
                    (),
                    RevisionGuard(Revision(1)),
                )
            else:
                epochs.start_epoch(uow, P, epoch(901), ())
        assert connection.total_changes == changes
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == row


def test_ap08_forgotten_complete_and_cross_uow_scope_refuse(state, producer):
    _, connection, session, _ = state
    row = register(session)
    selected_epoch = prepare_epoch(session)
    before = image(connection)
    scope = None
    with pytest.raises(StorageFailure), session.transaction() as uow:
        scope = effects(uow, row, producer, selected_epoch)
    assert scope not in actions._ENROLLED_SCOPES
    assert image(connection) == before
    with pytest.raises(StorageFailure), session.transaction() as uow:
        uow._action_scope = scope
        actions.complete_action(uow, P, executed(row), RevisionGuard(row.revision))
    assert get_action(state, row) == row


def test_ap02_ap09_current_guard_and_historical_full_row_replay_are_zero_write(
    state, producer
):
    _, connection, session, _ = state
    row = register(session)
    selected_epoch = prepare_epoch(session)
    execute(session, row, producer, selected_epoch)
    with session.transaction() as uow:
        policy.stop_thread(uow, P, T, Generation(1), NOW, ThreadStopReason.MANUAL_STOP)
        rule, version, sealed, member = rule_rows(revision=2, snapshot=2)
        policy.publish_rules(
            uow,
            P,
            (rule,),
            (replace(version, enabled=False),),
            sealed,
            (member,),
            RevisionGuard(Revision(1)),
        )
    actual = get_action(state, row)
    changes = connection.total_changes
    with session.transaction() as uow:
        receipt = actions.complete_action(
            uow, P, actual, RevisionGuard(actual.revision)
        )
    assert receipt.disposition == "replayed" and connection.total_changes == changes
    for incoming, guard in [
        (actual, RevisionGuard(Revision(0))),
        (row, RevisionGuard(actual.revision)),
        (
            replace(actual, observed_at=Timestamp(NOW.value + timedelta(seconds=1))),
            RevisionGuard(actual.revision),
        ),
        (replace(actual, event_id=lid(999)), RevisionGuard(actual.revision)),
    ]:
        with pytest.raises(StorageFailure), session.transaction() as uow:
            actions.complete_action(uow, P, incoming, guard)
    assert connection.total_changes == changes
    with view(state) as reader:
        assert not reader.get_thread(P, T).active
        assert reader.get_rule(P, lid(20)).current_revision == Revision(2)


def test_ap10_attention_is_terminal_and_cannot_hide_business_noops(state, producer):
    _, connection, session, _ = state
    publish(session)
    tracked, admitted = admit(session)
    row = register(session)
    attention = replace(
        row,
        state=ActionState.NEEDS_ATTENTION,
        error_code=ErrorCode.SOURCE_AUTH_REQUIRED,
        revision=Revision(1),
    )
    before = image(connection)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        policy.admit_thread(
            uow,
            P,
            tracked,
            admitted,
            (),
            ThreadGenerationGuardTracked("tracked", Generation(1)),
        )
        actions.complete_action(uow, P, attention, RevisionGuard(row.revision))
    assert image(connection) == before
    with session.transaction() as uow:
        actions.complete_action(uow, P, attention, RevisionGuard(row.revision))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        actions.complete_action(
            uow,
            P,
            replace(executed(row), revision=Revision(2)),
            RevisionGuard(Revision(1)),
        )
    assert get_action(state, row) == attention


def needs_attention(row):
    return replace(
        row,
        state=ActionState.NEEDS_ATTENTION,
        error_code=ErrorCode.SOURCE_AUTH_REQUIRED,
        revision=Revision(1),
    )


@pytest.mark.parametrize("attention_first", [False, True])
@pytest.mark.parametrize("caught", [False, True])
def test_ap10_attention_and_same_action_admission_both_orders_rollback_without_producer(
    state, attention_first, caught
):
    _, connection, session, _ = state
    assert actions._ACTION_PRODUCER_TYPES == ()
    row = register(session)
    attention = needs_attention(row)
    tracked, admission = thread_rows()
    admission = replace(
        admission,
        admission=AdmissionRefActionLabel("action_label", row.action_command_id),
    )
    before = image(connection)

    def compose(uow):
        if attention_first:
            actions.complete_action(uow, P, attention, RevisionGuard(row.revision))
        policy.admit_thread(
            uow, P, tracked, admission, (), ThreadGenerationGuardUntracked("untracked")
        )
        if not attention_first:
            actions.complete_action(uow, P, attention, RevisionGuard(row.revision))

    with pytest.raises(StorageFailure), session.transaction() as uow:
        if caught:
            with suppress(StorageFailure):
                compose(uow)
            assert uow._failed
        else:
            compose(uow)
    assert not uow._action_attention_completed
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == row
        with view(actual) as reader:
            assert reader.get_thread(P, T) is None


@pytest.mark.parametrize("operation", ["publish", "admit", "stop", "enqueue"])
@pytest.mark.parametrize("attention_first", [False, True])
@pytest.mark.parametrize("caught", [False, True])
def test_ap10_attention_business_participants_are_symmetric_and_after_guard_is_presql(
    state, operation, attention_first, caught
):
    _, connection, session, _ = state
    publish(session)
    tracked, admission = admit(session)
    selected_epoch = prepare_epoch(session)
    work = expansion(selected_epoch)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, work)
        old_member = _get(
            uow,
            P,
            "ruleset_members",
            (("ruleset_revision", Revision(1)), ("rule_id", lid(10))),
        )
    row = register(session)
    attention = needs_attention(row)
    before = image(connection)

    def business(uow):
        if operation == "publish":
            rule, version, sealed, member = rule_rows(n=21, snapshot=2)
            return policy.publish_rules(
                uow,
                P,
                (rule,),
                (version,),
                sealed,
                (replace(old_member, ruleset_revision=sealed.revision), member),
                RevisionGuard(Revision(1)),
            )
        if operation == "admit":
            return policy.admit_thread(
                uow,
                P,
                tracked,
                admission,
                (),
                ThreadGenerationGuardTracked("tracked", Generation(1)),
            )
        if operation == "stop":
            return policy.stop_thread(
                uow, P, T, Generation(1), NOW, ThreadStopReason.MANUAL_STOP
            )
        return jobs.enqueue(uow, P, work)

    def compose(uow):
        if attention_first:
            actions.complete_action(uow, P, attention, RevisionGuard(row.revision))
            statements = []
            connection.set_trace_callback(statements.append)
            try:
                with pytest.raises(StorageFailure) as denied:
                    business(uow)
                assert statements == []
                raise denied.value
            finally:
                connection.set_trace_callback(None)
        business(uow)
        actions.complete_action(uow, P, attention, RevisionGuard(row.revision))

    with pytest.raises(StorageFailure), session.transaction() as uow:
        if caught:
            with suppress(StorageFailure):
                compose(uow)
            assert uow._failed
        else:
            compose(uow)
    assert not uow._action_attention_completed
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == row
        # A separate untouched UoW still accepts the actual same business input.
        with actual[2].transaction() as ordinary:
            assert not ordinary._action_attention_completed
            receipt = business(ordinary)
            assert receipt.disposition == (
                "created"
                if operation == "publish"
                else "updated"
                if operation == "stop"
                else "replayed"
            )
        assert get_action(actual, row) == row


@pytest.mark.parametrize("caught", [False, True])
def test_ap10_attention_scope_entry_refuses_presql_and_poisons_marker(
    state, producer, caught
):
    _, connection, session, _ = state
    row = register(session)
    selected_epoch = prepare_epoch(session)
    work = expansion(selected_epoch)
    before = image(connection)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        actions.complete_action(
            uow, P, needs_attention(row), RevisionGuard(row.revision)
        )
        statements = []
        connection.set_trace_callback(statements.append)
        try:
            if caught:
                with pytest.raises(StorageFailure):
                    begin(uow, row, producer, work=work)
                assert uow._failed
            else:
                begin(uow, row, producer, work=work)
        finally:
            connection.set_trace_callback(None)
            assert statements == []
    assert uow._action_scope is None and not uow._action_attention_completed
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == row


@pytest.mark.parametrize("reactivate", [False, True])
@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize("caught", [False, True])
def test_ap10_stored_attention_cannot_create_or_reactivate_same_action_admission(
    state, reactivate, replay, caught
):
    _, connection, session, _ = state
    publish(session)
    if reactivate:
        admit(session)
        with session.transaction() as uow:
            policy.stop_thread(
                uow, P, T, Generation(1), NOW, ThreadStopReason.MANUAL_STOP
            )
    row = register(session)
    attention = needs_attention(row)
    with session.transaction() as uow:
        actions.complete_action(uow, P, attention, RevisionGuard(row.revision))
        assert reads.get_action(uow, P, row.action_command_id) == attention
    before = image(connection)
    tracked, admission = thread_rows(
        generation=3 if reactivate else 1, admission_revision=2 if reactivate else 1
    )
    unrelated = admission
    admission = replace(
        admission,
        admission=AdmissionRefActionLabel("action_label", row.action_command_id),
    )
    guard = (
        ThreadGenerationGuardTracked("tracked", Generation(2))
        if reactivate
        else ThreadGenerationGuardUntracked("untracked")
    )
    changes = connection.total_changes

    def attempt(uow):
        assert not uow._action_attention_completed
        if replay:
            receipt = actions.complete_action(
                uow, P, attention, RevisionGuard(Revision(1))
            )
            assert receipt.disposition == "replayed"
            assert not uow._action_attention_completed
        policy.admit_thread(uow, P, tracked, admission, (), guard)

    with pytest.raises(StorageFailure), session.transaction() as uow:
        if caught:
            with suppress(StorageFailure):
                attempt(uow)
            assert uow._failed
        else:
            attempt(uow)
    assert connection.total_changes == changes
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == attention
        # The unresolved action does not block unrelated, valid future-rule work.
        with actual[2].transaction() as ordinary:
            policy.admit_thread(ordinary, P, tracked, unrelated, (), guard)
        with view(actual) as reader:
            assert reader.get_thread(P, T) == tracked
        assert get_action(actual, row) == attention


def test_ap10_standalone_attention_allows_registration_event_bookkeeping_and_reads(
    state,
):
    _, connection, session, _ = state
    row = register(session)
    second_source = replace(
        event(701, thread=T, tag="label_changed"), processing=EventProcessing.RESOLVED
    )
    with session.transaction() as uow:
        _insert(uow, P, "source_events", second_source)
    second = action_row(701, source=second_source)
    attention = needs_attention(row)
    with session.transaction() as uow:
        actions.complete_action(uow, P, attention, RevisionGuard(row.revision))
        assert uow._action_attention_completed
        actions.register_action(uow, P, second)
        events.enrich_event(
            uow, P, second_source.event_id, T, RevisionGuard(Revision(0))
        )
        assert reads.get_action(uow, P, row.action_command_id) == attention
        assert reads.get_action(uow, P, second.action_command_id) == second
    assert not uow._action_attention_completed
    with reopen(state) as actual:
        assert get_action(actual, row) == attention
        assert get_action(actual, second) == second


def test_ap10_historical_attention_and_active_admission_replay_preserves_facts(
    state,
):
    _, connection, session, _ = state
    row = register(session)
    tracked, admission = thread_rows()
    admission = replace(
        admission,
        admission=AdmissionRefActionLabel("action_label", row.action_command_id),
    )
    # Retained preexisting authorization is not silently revoked by this repair.
    with session.transaction() as uow:
        policy.admit_thread(
            uow, P, tracked, admission, (), ThreadGenerationGuardUntracked("untracked")
        )
    attention = needs_attention(row)
    with session.transaction() as uow:
        actions.complete_action(uow, P, attention, RevisionGuard(row.revision))
    before = image(connection)
    changes = connection.total_changes
    with session.transaction() as uow:
        receipt = actions.complete_action(uow, P, attention, RevisionGuard(Revision(1)))
        assert receipt == WriteReceipt("replayed", row.action_command_id, Revision(1))
        assert not uow._action_attention_completed
        replayed = policy.admit_thread(
            uow,
            P,
            tracked,
            admission,
            (),
            ThreadGenerationGuardTracked("tracked", Generation(1)),
        )
        assert replayed.disposition == "replayed"
    assert connection.total_changes == changes
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == attention


@pytest.mark.parametrize(
    "bad",
    ["backwards", "pending_patch", "attention_without_error", "revision", "overflow"],
)
def test_ap10_invalid_transition_and_revision_refuse(state, bad):
    _, connection, session, _ = state
    row = register(session)
    if bad == "overflow":
        connection.execute("UPDATE action_commands SET revision=?", (MAX_INTEGER,))
        row = replace(row, revision=Revision(MAX_INTEGER))
    candidate = executed(row)
    if bad == "backwards":
        candidate = executed(row, at=Timestamp(NOW.value - timedelta(seconds=1)))
    elif bad == "pending_patch":
        candidate = replace(
            row, error_code=ErrorCode.SOURCE_AUTH_REQUIRED, revision=Revision(1)
        )
    elif bad == "attention_without_error":
        candidate = replace(
            row, state=ActionState.NEEDS_ATTENTION, revision=Revision(1)
        )
    elif bad == "revision":
        candidate = replace(candidate, revision=Revision(2))
    with pytest.raises(StorageFailure), session.transaction() as uow:
        actions.complete_action(uow, P, candidate, RevisionGuard(row.revision))
    assert get_action(state, row) == row


def set_mode(session, mode):
    # Test-only synthetic mode fixture, not an allocated M5 CLI/provider.
    with session.transaction() as uow:
        uow._execute(
            "UPDATE projections SET source_mode=? WHERE projection_id=?",
            (mode.value, P.value),
        )


def cleanup(session, row, target, error=None):
    with session.transaction() as uow:
        old = reads.get_action(uow, P, row.action_command_id)
        return actions.record_cleanup(
            uow, P, row.action_command_id, target, error, RevisionGuard(old.revision)
        )


@pytest.mark.parametrize("mode", list(SourceMode))
@pytest.mark.parametrize("origin", list(CleanupState))
@pytest.mark.parametrize("target", list(CleanupState))
@pytest.mark.parametrize("error", [None, ErrorCode.SOURCE_AUTH_REQUIRED])
def test_ap11_full_cleanup_matrix_changes_only_cleanup_fields(
    state, producer, mode, origin, target, error
):
    _, connection, session, _ = state
    row = register(session, kind=ActionKind.BLACKLIST)
    execute(session, row, producer)
    set_mode(session, SourceMode.CONVENIENCE)
    if origin is not CleanupState.NOT_REQUESTED:
        cleanup(session, row, CleanupState.QUEUED)
    if origin is CleanupState.BLOCKED:
        cleanup(session, row, origin, ErrorCode.SOURCE_AUTH_REQUIRED)
    elif origin is CleanupState.COMPLETED:
        cleanup(session, row, origin)
    set_mode(session, mode)
    old = get_action(state, row)
    before = image(connection)
    changes = connection.total_changes
    replay = (origin, old.error_code) == (target, error)
    transition = (
        origin is CleanupState.QUEUED
        and target is CleanupState.BLOCKED
        and error is not None
    ) or (
        mode is SourceMode.CONVENIENCE
        and error is None
        and (
            (
                origin in {CleanupState.NOT_REQUESTED, CleanupState.BLOCKED}
                and target is CleanupState.QUEUED
            )
            or (origin is CleanupState.QUEUED and target is CleanupState.COMPLETED)
        )
    )
    if not (replay or transition):
        with pytest.raises(StorageFailure):
            cleanup(session, row, target, error)
        assert image(connection) == before
    else:
        receipt = cleanup(session, row, target, error)
        actual = get_action(state, row)
        expected = replace(
            old,
            cleanup=target,
            error_code=error,
            revision=old.revision if replay else Revision(old.revision.value + 1),
        )
        assert actual == expected and receipt.revision == expected.revision
        assert receipt.disposition == ("replayed" if replay else "updated")
        if replay:
            assert connection.total_changes == changes
        for table, values in before.items():
            if table != "action_commands":
                assert image(connection)[table] == values


def test_ap11_cleanup_guard_precedes_exact_replay_and_no_business_reset(
    state, producer
):
    _, connection, session, _ = state
    pending_row = register(session)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        actions.record_cleanup(
            uow,
            P,
            pending_row.action_command_id,
            CleanupState.NOT_REQUESTED,
            None,
            RevisionGuard(Revision(0)),
        )
    row = register(session, 701, kind=ActionKind.BLACKLIST)
    execute(session, row, producer)
    before = image(connection)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        actions.record_cleanup(
            uow,
            P,
            row.action_command_id,
            CleanupState.NOT_REQUESTED,
            None,
            RevisionGuard(Revision(0)),
        )
    assert image(connection) == before


@pytest.mark.parametrize(
    "inflight", ["prepared", "dispatched", "pending", "known", "mapped"]
)
def test_ap06_blacklist_stops_only_selected_generation_preserving_real_intents_and_maps(
    state, producer, inflight
):
    from test_db_mappings import inserted, verify
    from test_db_results import pending, ready, record

    _, connection, session, _ = state
    if inflight == "mapped":
        original, _, acquired, attempt = inserted(state)
        verify(state, attempt)
        with view(state) as reader:
            attempt = reader.get_attempt(P, attempt.attempt_id)
    else:
        original, _, acquired, attempt = ready(state, dispatched=inflight != "prepared")
        if inflight == "pending":
            attempt = pending(attempt)
            record(state, attempt)
        elif inflight == "known":
            from test_db_results import known

            attempt = known(attempt)
            record(state, attempt)
    other = ProviderId("synthetic-unselected-thread")
    admit(session, thread=other)
    selected_unsent = job(980)
    other_job = job(981, thread=other)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, selected_unsent)
        jobs.enqueue(uow, P, other_job)
    row = register(session, kind=ActionKind.BLACKLIST)
    protected = {
        name: tuple(connection.execute("SELECT * FROM " + name).fetchall())
        for name in (
            "message_mappings",
            "mapping_history",
            "target_ownership",
            "thread_targets",
        )
    }
    original_claim = connection.execute(
        "SELECT * FROM job_claims WHERE job_id=?", (original.job_id.value,)
    ).fetchone()
    with view(state) as reader:
        original_job = reader.get_job(P, original.job_id)
    execute(session, row, producer)
    with reopen(state) as actual:
        assert get_action(actual, row) == executed(row)
        with view(actual) as reader:
            stopped = reader.get_thread(P, T)
            assert not stopped.active and stopped.generation == Generation(2)
            assert stopped.stop_reason is ThreadStopReason.BLACKLIST
            assert reader.get_thread(P, other).active
            assert reader.get_job(P, selected_unsent.job_id).state is JobState.CANCELLED
            assert reader.get_job(P, other_job.job_id) == other_job
            factual = reader.get_attempt(P, attempt.attempt_id)
            if inflight == "prepared":
                assert factual.state.value == "cancelled_before_dispatch"
                assert reader.get_job(P, original.job_id).state is JobState.CANCELLED
            else:
                assert factual == attempt
                claim_row = (
                    actual[1]
                    .execute(
                        "SELECT * FROM job_claims WHERE job_id=?",
                        (original.job_id.value,),
                    )
                    .fetchone()
                )
                assert claim_row == original_claim
                assert reader.get_job(P, original.job_id) == original_job
        for name, values in protected.items():
            assert (
                tuple(actual[1].execute("SELECT * FROM " + name).fetchall()) == values
            )


@pytest.mark.parametrize("stopped", [False, True])
def test_ap06_absent_or_stopped_blacklist_preserves_absence_or_all_old_facts(
    state, producer, stopped
):
    _, connection, session, _ = state
    if stopped:
        publish(session)
        tracked, _ = admit(session)
        with session.transaction() as uow:
            policy.stop_thread(
                uow, P, T, tracked.generation, NOW, ThreadStopReason.MANUAL_STOP
            )
    before = tuple(connection.execute("SELECT * FROM tracked_threads").fetchall())
    admissions = tuple(connection.execute("SELECT * FROM thread_admissions").fetchall())
    row = register(session, kind=ActionKind.BLACKLIST)
    execute(session, row, producer)
    assert (
        tuple(connection.execute("SELECT * FROM tracked_threads").fetchall()) == before
    )
    assert (
        tuple(connection.execute("SELECT * FROM thread_admissions").fetchall())
        == admissions
    )


@pytest.mark.parametrize(
    "target,verb",
    [
        ("tracked_threads", "UPDATE"),
        ("insert_attempts", "UPDATE"),
        ("job_claims", "DELETE"),
        ("sync_jobs", "UPDATE"),
        ("action_commands", "UPDATE"),
    ],
)
def test_ap08_blacklist_after_sql_abort_and_caught_failure_preserve_pre_group(
    state, producer, target, verb
):
    from test_db_results import ready

    _, connection, session, _ = state
    ready(state, dispatched=False)
    row = register(session, kind=ActionKind.BLACKLIST)
    before = image(connection)
    connection.execute(
        f"CREATE TEMP TRIGGER fail_blacklist AFTER {verb} ON {target} "
        "BEGIN SELECT RAISE(ABORT,'synthetic-blacklist-failure'); END"
    )
    with (
        pytest.raises(StorageFailure),
        session.transaction() as uow,
        suppress(StorageFailure),
    ):
        effects(uow, row, producer)
        actions.complete_action(uow, P, executed(row), RevisionGuard(row.revision))
    with reopen(state) as actual:
        assert image(actual[1]) == before
        assert get_action(actual, row) == row


def seed_members(session, count=2):
    """Test-only complete relation allocation beyond the public batch cap.

    Each exact row uses actual strict schema/FKs/UoW/commit guards. This is not
    a production bulk producer or an expansion of publish_rules' API.
    """
    members = []
    with session.transaction() as uow:
        _insert(uow, P, "rulesets", RulesetRow(P, Revision(1), NOW, False))
        for n in range(1000, 1000 + count):
            rule, version, _, _ = rule_rows(n=n)
            _insert(uow, P, "rules", rule)
            _insert(uow, P, "rule_revisions", version)
            member = RulesetMemberRow(
                P, Revision(1), rule.rule_id, rule.current_revision
            )
            _insert(uow, P, "ruleset_members", member)
            members.append(member)
        uow._execute(
            "UPDATE rulesets SET sealed=1 WHERE projection_id=? AND revision=1",
            (P.value,),
        )
        uow._execute(
            "UPDATE projections SET ruleset_revision=1 WHERE projection_id=?",
            (P.value,),
        )
    return tuple(members)


@pytest.mark.parametrize(
    "difference",
    [
        "identical",
        "drop",
        "change",
        "add",
        "late_drop",
        "nonselected_rule",
        "nonselected_revision",
    ],
)
def test_ap07_complete_bidirectional_nonselected_membership_not_truncated(
    state, producer, difference
):
    _, connection, session, _ = state
    old_members = seed_members(session, 501 if difference == "late_drop" else 2)
    row = register(session)
    selected_epoch = prepare_epoch(session)
    work = expansion(selected_epoch)
    before = image(connection)
    rule, version, sealed, selected = rule_rows(snapshot=2)
    carried = tuple(
        replace(value, ruleset_revision=Revision(2)) for value in old_members
    )
    rules, revisions = (rule,), (version,)
    if difference == "drop":
        carried = carried[:1]
    elif difference == "change":
        with session.transaction() as uow:
            _insert(
                uow,
                P,
                "rule_revisions",
                replace(version, rule_id=lid(1001), revision=Revision(2)),
            )
        before = image(connection)
        carried = (carried[0], replace(carried[1], rule_revision=Revision(2)))
    elif difference == "add":
        with session.transaction() as uow:
            extra_rule, extra_version, _, _ = rule_rows(n=2000)
            _insert(uow, P, "rules", extra_rule)
            _insert(uow, P, "rule_revisions", extra_version)
        before = image(connection)
        carried += (RulesetMemberRow(P, Revision(2), lid(2000), Revision(1)),)
    elif difference == "late_drop":
        # 499 retained + selected == the existing 500-row batch cap. Omitted
        # old members beyond a normal list's page must still refuse.
        carried = carried[:499]
    elif difference == "nonselected_rule":
        rules += (rule_rows(n=1000, revision=2)[0],)
    elif difference == "nonselected_revision":
        revisions += (rule_rows(n=1000, revision=2)[1],)

    def compose():
        with session.transaction() as uow:
            begin(uow, row, producer, work=work)
            policy.publish_rules(
                uow,
                P,
                rules,
                revisions,
                sealed,
                (*carried, selected),
                RevisionGuard(Revision(1)),
            )
            tracked, admitted = thread_rows()
            admitted = replace(
                admitted,
                admission=AdmissionRefActionLabel(
                    "action_label", row.action_command_id
                ),
            )
            policy.admit_thread(
                uow,
                P,
                tracked,
                admitted,
                (),
                ThreadGenerationGuardUntracked("untracked"),
            )
            jobs.enqueue(uow, P, work)
            actions.complete_action(uow, P, executed(row), RevisionGuard(row.revision))

    if difference == "identical":
        compose()
        assert get_action(state, row) == executed(row)
        assert connection.execute(
            "SELECT COUNT(*) FROM ruleset_members WHERE ruleset_revision=2"
        ).fetchone() == (3,)
    else:
        with pytest.raises(StorageFailure):
            compose()
        with reopen(state) as actual:
            assert image(actual[1]) == before
            assert get_action(actual, row) == row


@pytest.mark.parametrize(
    "bad",
    [
        "kind",
        "revision",
        "disabled",
        "member",
        "empty_work",
        "fake_receipt",
        "other_thread",
        "other_job",
        "other_epoch",
        "terminal",
        "stale_generation",
        "claim",
        "retry_deadline",
        "blocked_error",
        "second_enqueue",
        "second_admit",
    ],
)
def test_ap07_wrong_selected_facts_missing_receipt_and_unrelated_work_refuse(
    state, producer, bad
):
    _, connection, session, _ = state
    publish(session)
    tracked, admitted = admit(session)
    selected_epoch = prepare_epoch(session)
    work = expansion(selected_epoch)
    if bad in {
        "terminal",
        "stale_generation",
        "claim",
        "retry_deadline",
        "blocked_error",
        "fake_receipt",
    }:
        with session.transaction() as uow:
            jobs.enqueue(uow, P, work)
        if bad == "terminal":
            connection.execute("UPDATE sync_jobs SET state='completed'")
        elif bad == "stale_generation":
            with session.transaction() as uow:
                policy.stop_thread(
                    uow, P, T, Generation(1), NOW, ThreadStopReason.MANUAL_STOP
                )
                next_thread, next_admission = thread_rows(
                    generation=3, admission_revision=2
                )
                policy.admit_thread(
                    uow,
                    P,
                    next_thread,
                    next_admission,
                    (),
                    ThreadGenerationGuardTracked("tracked", Generation(2)),
                )
        elif bad == "retry_deadline":
            connection.execute(
                "UPDATE sync_jobs SET state='retry_wait',"
                "last_error_code='network_unavailable'"
            )
        elif bad == "blocked_error":
            connection.execute("UPDATE sync_jobs SET state='blocked'")
    if bad == "disabled":
        publish(session, enabled=False, revision=2)
    elif bad == "member":
        with session.transaction() as uow:
            policy.publish_rules(
                uow,
                P,
                (),
                (),
                RulesetRow(P, Revision(2), NOW, True),
                (),
                RevisionGuard(Revision(1)),
            )
    row = register(
        session, kind=ActionKind.ADD_DOMAIN if bad == "kind" else ActionKind.ADD_SENDER
    )
    before = image(connection)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        scope = begin(
            uow,
            row,
            producer,
            rule_id=10,
            rule_revision=2 if bad in {"revision", "disabled"} else 1,
            work=work,
        )
        if bad == "fake_receipt":
            with pytest.raises(FrozenInstanceError):
                scope.enqueue_receipt = WriteReceipt(
                    "replayed", work.job_id, Revision(0)
                )
        elif bad != "empty_work":
            candidate = work
            if bad == "other_thread":
                candidate = expansion(selected_epoch, thread=ProviderId("other-thread"))
            elif bad == "other_job":
                candidate = replace(work, job_id=lid(951))
            elif bad == "other_epoch":
                candidate = expansion(replace(selected_epoch, epoch_id=lid(999)))
            jobs.enqueue(uow, P, candidate)
        if bad == "second_enqueue":
            jobs.enqueue(uow, P, work)
        elif bad == "claim":
            uow._execute(
                "UPDATE sync_jobs SET state='claimed' WHERE job_id=?",
                (work.job_id.value,),
            )
        elif bad == "second_admit":
            for _ in range(2):
                policy.admit_thread(
                    uow,
                    P,
                    tracked,
                    admitted,
                    (),
                    ThreadGenerationGuardTracked("tracked", Generation(1)),
                )
        actions.complete_action(uow, P, executed(row), RevisionGuard(row.revision))
    assert image(connection) == before
    assert get_action(state, row) == row


@pytest.mark.parametrize(
    "status", [JobState.QUEUED, JobState.CLAIMED, JobState.RETRY_WAIT, JobState.BLOCKED]
)
def test_ap05_valid_existing_expansion_states_use_actual_replay_and_keep_first_origin(
    state, producer, status
):
    _, connection, session, info = state
    publish(session)
    admit(session)
    selected_epoch = prepare_epoch(session)
    first_origin = prepare_epoch(session, n=901)
    work = expansion(selected_epoch, n=951)
    original = replace(work, origin_epoch_id=first_origin.epoch_id)
    with session.transaction() as uow:
        jobs.enqueue(uow, P, original)
    if status is JobState.CLAIMED:
        ready_test_metadata(connection, session)
        claim(session, info, original)
    elif status in {JobState.RETRY_WAIT, JobState.BLOCKED}:
        with session.transaction() as uow:
            jobs.defer_job(
                uow,
                P,
                original.job_id,
                status.value,
                ErrorCode.NETWORK_UNAVAILABLE,
                Timestamp(NOW.value + timedelta(seconds=5))
                if status is JobState.RETRY_WAIT
                else None,
                RevisionGuard(Revision(0)),
            )
    row = register(session)
    execute(
        session,
        row,
        producer,
        selected_epoch,
        new_rule=False,
        work=replace(work, job_id=lid(950)),
    )
    with view(state) as reader:
        actual = reader.get_job(P, original.job_id)
        assert (
            actual.state is status and actual.origin_epoch_id == first_origin.epoch_id
        )
        assert actual.job_id == original.job_id
    assert connection.execute(
        "SELECT COUNT(*) FROM epoch_jobs WHERE job_id=?", (original.job_id.value,)
    ).fetchone() == (2,)


def test_ap03_scope_entry_refuses_prior_business_touch_and_unregistered_subclass(
    state, producer
):
    _, connection, session, _ = state
    publish(session)
    tracked, admitted = admit(session)
    row = register(session)
    selected_epoch = prepare_epoch(session)
    before = image(connection)
    with pytest.raises(StorageFailure), session.transaction() as uow:
        policy.admit_thread(
            uow,
            P,
            tracked,
            admitted,
            (),
            ThreadGenerationGuardTracked("tracked", Generation(1)),
        )
        begin(uow, row, producer, rule_id=10, work=expansion(selected_epoch))

    class SubclassProducer(SyntheticActionProducer):
        pass

    with (
        pytest.raises(StorageFailure, match="owner_unavailable"),
        session.transaction() as uow,
    ):
        begin(uow, row, SubclassProducer(), rule_id=10, work=expansion(selected_epoch))
    assert image(connection) == before


def test_ap12_sensitive_payloads_errors_and_provider_exceptions_never_enter_sinks(
    state, caplog, capsys
):
    path, connection, session, _ = state
    row = register(session)
    sentinels = markers()
    for marker in sentinels:
        with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
            actions.record_cleanup(
                uow,
                P,
                row.action_command_id,
                CleanupState.QUEUED,
                marker.value,
                RevisionGuard(row.revision),
            )
        assert caught.value.code is ErrorCode.INVALID_INPUT
        assert_private_boundary(
            str(caught.value) + repr(caught.value), sentinels, Profile.LOG
        )
        with pytest.raises(StorageFailure) as caught:
            replace(row, error_code=marker.value)
        assert_private_boundary(
            str(caught.value) + repr(caught.value), sentinels, Profile.LOG
        )
    # A provider-like synthetic failure AFTER a real write must expose only a
    # fixed numeric error mapping, never the unfiltered SQL exception text.
    text = next(value.value for value in sentinels if value.kind.value == "output_only")
    escaped = text.replace("'", "''")
    connection.execute(
        "CREATE TEMP TRIGGER fail_private_action AFTER UPDATE ON action_commands "
        f"BEGIN SELECT RAISE(ABORT,'{escaped}'); END"
    )
    attention = replace(
        row,
        state=ActionState.NEEDS_ATTENTION,
        error_code=ErrorCode.SOURCE_AUTH_REQUIRED,
        revision=Revision(1),
    )
    with pytest.raises(StorageFailure) as caught, session.transaction() as uow:
        actions.complete_action(uow, P, attention, RevisionGuard(row.revision))
    assert_private_boundary(
        str(caught.value) + repr(caught.value), sentinels, Profile.LOG
    )
    assert get_action(state, row) == row
    inspect_sqlite(connection, sentinels)
    inspect_files(
        path.parent,
        [value for value in path.parent.iterdir() if value.is_file()],
        sentinels,
    )
    assert_private_boundary(caplog.text, sentinels, Profile.LOG)
    captured = capsys.readouterr()
    assert_private_boundary(captured.out + captured.err, sentinels, Profile.PUBLIC)
    assert connection.execute("SELECT COUNT(*) FROM audit_events").fetchone() == (0,)
