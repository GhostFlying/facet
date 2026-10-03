"""SI04/A1: exact passive fields, closed errors and no authority by metadata."""

from dataclasses import FrozenInstanceError, fields, replace

import pytest
from test_command_bootstrap_storage import command_seed, expect_fixed
from unit.test_db_schema import NOW, P, bootstrap_rows, lid

from facet.contracts import Count, ErrorCode, OperationState, Revision, Role
from facet.db.codecs import SchemaVersion, StorageFailure
from facet.db.command_records import (
    AuthCommand,
    AuthPayloadRow,
    BootstrapCommand,
    BootstrapInspection,
    BootstrapPayloadRow,
    CommandRuntimeRow,
    ControlPayloadRow,
    EnabledCommand,
    FreshCommandBootstrap,
    LocalCommandKind,
    OperationRow,
    RequestId,
    ShutdownPhase,
)


def operation(*, prior=False):
    seed = command_seed(prior=prior)
    return OperationRow(
        P,
        seed.operation_id,
        seed.namespace,
        seed.nonce,
        LocalCommandKind(seed.command.value),
        1,
        1,
        seed.digest,
        OperationState.COMPLETED,
        Revision(1),
        NOW,
        NOW,
        NOW,
        None,
        True,
        Revision(0),
        Revision(0),
        None,
        True,
        False,
    )


def payload(*, prior=False):
    seed = command_seed(prior=prior)
    return BootstrapPayloadRow(
        P,
        seed.operation_id,
        seed.config_semantic_digest,
        seed.config_artifact_digest,
        RequestId(f"rq1_{seed.namespace.value}_{seed.nonce.value}"),
        None if prior else Count(2),
    )


VALUES = (
    RequestId(f"rq1_{lid(3).value}_{lid(4).value}"),
    CommandRuntimeRow(
        P, Revision(1), Revision(0), lid(1), ShutdownPhase.IDLE, None, None
    ),
    operation(),
    ControlPayloadRow(P, lid(10), True, False, Revision(0), Revision(1)),
    payload(),
    AuthPayloadRow(
        P, lid(10), Role.SOURCE, Revision(0), Revision(1), Revision(0), None
    ),
    command_seed(),
    FreshCommandBootstrap(command_seed(), command_seed(prior=True)),
    BootstrapInspection(
        SchemaVersion(2),
        bootstrap_rows()[0],
        operation(),
        payload(),
        operation(prior=True),
        payload(prior=True),
    ),
)


@pytest.mark.parametrize("record", VALUES)
def test_actual_full_records_are_frozen_sealed_and_exact(record):
    assert repr(record) == str(record) == type(record).__name__ + "()"
    assert replace(record) == record
    with pytest.raises(FrozenInstanceError):
        setattr(record, fields(record)[0].name, object())
    assert not hasattr(record, "__dict__")


@pytest.mark.parametrize(
    "record,field",
    [(record, field.name) for record in VALUES for field in fields(record)],
)
def test_every_field_rejects_wrong_actual_class_without_exception_context(
    record, field
):
    expect_fixed(lambda: replace(record, **{field: object()}), ErrorCode.INVALID_INPUT)


@pytest.mark.parametrize("record", VALUES)
def test_unknown_missing_duplicate_and_surplus_constructor_fields_are_sealed(record):
    cls = type(record)
    values = tuple(getattr(record, field.name) for field in fields(record))
    for invoke in (
        lambda: cls(*values, object()),
        lambda: cls(*values[:-1]),
        lambda: cls(*values, unapproved="synthetic content"),
        lambda: cls(*values, **{fields(record)[0].name: values[0]}),
    ):
        expect_fixed(invoke, ErrorCode.INVALID_INPUT)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "rq1_",
        "rq2_" + lid(3).value + "_" + lid(4).value,
        "rq1_" + lid(0xAB).value.upper() + "_" + lid(4).value,
        "rq1_" + "0" * 32 + "_" + lid(4).value,
        "rq1_" + lid(3).value + "_" + "f" * 32,
        "rq1_" + lid(3).value + "_" + lid(4).value + "\x00",
    ],
)
def test_request_id_is_exact_lowercase_uuid4_pair(text):
    expect_fixed(lambda: RequestId(text), ErrorCode.INVALID_INPUT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("payload_version", True),
        ("digest_version", True),
        ("payload_version", 2),
        ("revision", Revision(0)),
        ("completed_at", None),
        ("expected_preview_id", lid(80)),
        ("confirmation_yes", False),
        ("duplicate_risk_acknowledged", True),
        ("state", OperationState.ACCEPTED),
        ("code", "synthetic private exception"),
    ],
)
def test_operation_tag_nullness_and_confirmation_invariants(field, value):
    expect_fixed(
        lambda: replace(operation(), **{field: value}), ErrorCode.INVALID_INPUT
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("command", BootstrapCommand.CONFIG_INIT),
        ("expected_binding_revision", Revision(1)),
        ("expected_config_revision", Revision(1)),
        ("digest_version", True),
        ("confirmation_yes", False),
        ("duplicate_risk_acknowledged", True),
    ],
)
def test_fresh_current_seed_guards(field, value):
    def invoke():
        seed = replace(command_seed(), **{field: value})
        return FreshCommandBootstrap(seed, None)

    expect_fixed(invoke, ErrorCode.INVALID_INPUT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("namespace", lid(90)),
        ("nonce", lid(4)),
        ("operation_id", lid(10)),
        ("config_semantic_digest", command_seed().digest),
        ("command", BootstrapCommand.FACET_INIT),
    ],
)
def test_prior_config_must_share_lineage_but_have_distinct_original_identity(
    field, value
):
    expect_fixed(
        lambda: FreshCommandBootstrap(
            command_seed(), replace(command_seed(prior=True), **{field: value})
        ),
        ErrorCode.INVALID_INPUT,
    )


def test_inspection_exact_six_fields_and_nullable_pairs():
    assert tuple(field.name for field in fields(BootstrapInspection)) == (
        "schema_version",
        "owner",
        "current_operation",
        "current_payload",
        "prior_operation",
        "prior_payload",
    )
    blank = BootstrapInspection(
        SchemaVersion(2), bootstrap_rows()[0], None, None, None, None
    )
    for change in (
        {"schema_version": SchemaVersion(1)},
        {"schema_version": Count(2)},
        {"current_operation": operation()},
        {"prior_payload": payload(prior=True)},
        {
            "current_operation": operation(prior=True),
            "current_payload": payload(prior=True),
        },
    ):
        expect_fixed(
            lambda change=change: replace(blank, **change), ErrorCode.INVALID_INPUT
        )


def test_passive_auth_control_kinds_have_no_executor_or_registration():
    assert {kind.value for kind in LocalCommandKind} == (
        {kind.value for kind in EnabledCommand}
        | {kind.value for kind in AuthCommand}
        | {kind.value for kind in BootstrapCommand}
    )
    from facet.db import migration_entry, read_views

    assert migration_entry._MIGRATION_PROVIDER_TYPES == ()
    assert read_views._PROVIDER_TYPES == ()


@pytest.mark.parametrize("value", [True, -1, 2**63])
def test_core_numeric_overflow_is_not_an_accepted_command_count(value):
    with pytest.raises(ValueError):
        Revision(value)


@pytest.mark.parametrize("record", VALUES)
def test_actual_record_subclass_cannot_bypass_closed_constructor(record):
    foreign = type("UnapprovedRecord", (type(record),), {})
    values = tuple(getattr(record, field.name) for field in fields(record))
    expect_fixed(lambda: foreign(*values), ErrorCode.INVALID_INPUT)


@pytest.mark.parametrize(
    "variant", ["local_subclass", "schema_subclass", "named_owner"]
)
def test_actual_foreign_scalar_or_named_metadata_is_not_coerced(variant):
    from facet.contracts import LocalId

    if variant == "local_subclass":
        foreign = type("ForeignLocalId", (LocalId,), {})(lid(3).value)
        expect_fixed(
            lambda: replace(command_seed(), namespace=foreign), ErrorCode.INVALID_INPUT
        )
    elif variant == "schema_subclass":
        foreign = type("ForeignSchemaVersion", (SchemaVersion,), {})(2)
        expect_fixed(
            lambda: BootstrapInspection(
                foreign, bootstrap_rows()[0], None, None, None, None
            ),
            ErrorCode.INVALID_INPUT,
        )
    else:
        # Matching a real type's name/attributes is data, not its exact class.
        foreign = type("OwnerSessionInfo", (), {})()
        owner = bootstrap_rows()[0]
        for field in fields(owner):
            setattr(foreign, field.name, getattr(owner, field.name))
        expect_fixed(
            lambda: BootstrapInspection(
                SchemaVersion(2), foreign, None, None, None, None
            ),
            ErrorCode.INVALID_INPUT,
        )


@pytest.mark.parametrize("variant", ["binding_guard", "schema_count"])
def test_boolean_cannot_be_a_closed_command_revision_or_count(variant):
    if variant == "binding_guard":
        expect_fixed(
            lambda: replace(VALUES[1], binding_guard=True), ErrorCode.INVALID_INPUT
        )
    else:
        expect_fixed(
            lambda: replace(payload(), initialized_schema_version=True),
            ErrorCode.INVALID_INPUT,
        )


@pytest.mark.parametrize("record", VALUES)
def test_exact_builtin_keyword_names_preserve_every_record(record):
    kwargs = {field.name: getattr(record, field.name) for field in fields(record)}
    assert all(type(name) is str for name in kwargs)
    assert type(record)(**kwargs) == record


@pytest.mark.parametrize("record", VALUES)
@pytest.mark.parametrize("caller_context", [False, True])
@pytest.mark.parametrize("hook_behavior", ["raise", "equal", "unequal"])
def test_foreign_keyword_names_refuse_before_facet_hooks(
    record, caller_context, hook_behavior
):
    # A genuine **kwargs str-subclass key survives Python's call binder. Its
    # possible pre-entry comparison to the implicit cls argument is benign;
    # count only the hook that the historical Facet membership invoked.
    hooks = []
    sentinel = "SYNTHETIC_PRIVATE_COMMAND_KEYWORD_ERROR"

    class ForeignKey(str):
        __hash__ = str.__hash__

        def __eq__(self, other):
            if type(other) is str and other == "cls":
                return str.__eq__(self, other)
            hooks.append("foreign_equality")
            if hook_behavior == "raise":
                raise ValueError(sentinel)
            return hook_behavior == "equal"

    names = tuple(field.name for field in fields(record))
    kwargs = {
        ForeignKey(names[0]): getattr(record, names[0]),
        **{name: getattr(record, name) for name in names[1:]},
    }
    assert type(next(iter(kwargs))) is ForeignKey

    def observe():
        try:
            type(record)(**kwargs)
        except BaseException as error:
            entered_facet = False
            traceback = error.__traceback__
            while traceback is not None:
                frame = traceback.tb_frame
                entered_facet |= (
                    frame.f_code.co_name == "__call__"
                    and frame.f_globals.get("__name__") == "facet.db.command_records"
                )
                traceback = traceback.tb_next
            # Only fixed observations survive: no private exception is retained
            # or included in an assertion's outward diagnostic.
            return {
                "entered_facet": entered_facet,
                "hook_calls": len(hooks),
                "fixed_failure": type(error) is StorageFailure,
                "fixed_code": getattr(error, "code", None) is ErrorCode.INVALID_INPUT,
                "fixed_text": str(error) == ErrorCode.INVALID_INPUT.value,
                "private_text": sentinel in str(error) or sentinel in repr(error),
                "cause": error.__cause__ is not None,
                "context": error.__context__ is not None,
            }
        return {"unexpected_success": True, "hook_calls": len(hooks)}

    if caller_context:
        try:
            raise ValueError(sentinel)
        except ValueError:
            facts = observe()
    else:
        facts = observe()
    assert facts == {
        "entered_facet": True,
        "hook_calls": 0,
        "fixed_failure": True,
        "fixed_code": True,
        "fixed_text": True,
        "private_text": False,
        "cause": False,
        "context": False,
    }
