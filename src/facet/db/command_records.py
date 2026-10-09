"""Closed passive command-storage values. Construction grants no authority."""

import re
from dataclasses import dataclass, fields
from datetime import timedelta
from enum import StrEnum
from functools import cache
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints

from facet.contracts import (
    Count,
    ErrorCode,
    LocalId,
    OperationState,
    PreviewPurpose,
    ProjectionId,
    ProviderId,
    Revision,
    Role,
    Sha256Hex,
    Timestamp,
)

from .codecs import SchemaVersion, StorageFailure
from .models import OwnerSessionInfo


def _fail(code=ErrorCode.INVALID_INPUT):
    try:
        raise StorageFailure(code) from None
    except StorageFailure as error:
        error.__cause__ = None
        error.__context__ = None
        raise


def _six_calendar_month_start(value):
    month = value.year * 12 + value.month - 1 - 6
    year, month = divmod(month, 12)
    return value.replace(
        year=year,
        month=month + 1,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _valid_backfill_window(window_start, window_end, accepted_at):
    return window_end.value == accepted_at.value and window_start.value <= (
        _six_calendar_month_start(window_end.value)
    )


class EnabledCommand(StrEnum):
    DAEMON_PAUSE = "daemon_pause"
    DAEMON_RESUME = "daemon_resume"
    DAEMON_SHUTDOWN = "daemon_shutdown"


class BootstrapCommand(StrEnum):
    CONFIG_INIT = "config_init"
    FACET_INIT = "facet_init"


class AuthCommand(StrEnum):
    AUTHORIZE = "auth_authorize"
    REAUTHORIZE = "auth_reauthorize"


class LocalCommandKind(StrEnum):
    DAEMON_PAUSE = "daemon_pause"
    DAEMON_RESUME = "daemon_resume"
    DAEMON_SHUTDOWN = "daemon_shutdown"
    CONFIG_INIT = "config_init"
    FACET_INIT = "facet_init"
    AUTH_AUTHORIZE = "auth_authorize"
    AUTH_REAUTHORIZE = "auth_reauthorize"
    BACKFILL_PREVIEW = "backfill_preview"
    BACKFILL_START = "backfill_start"


class ShutdownPhase(StrEnum):
    IDLE = "idle"
    REQUESTED = "requested"
    DRAINING = "draining"


@cache
def _hints(cls):
    return get_type_hints(cls)


def _matches(value, annotation):
    if get_origin(annotation) is Literal:
        return any(type(value) is type(a) and value == a for a in get_args(annotation))
    if get_origin(annotation) is UnionType:
        return any(_matches(value, a) for a in get_args(annotation))
    return type(value) is annotation


class _RecordType(type):
    def __call__(cls, *args, **kwargs):
        if cls not in _RECORD_TYPES:
            _fail()
        if any(type(name) is not str for name in kwargs):
            _fail()
        names = tuple(f.name for f in fields(cls))
        if (
            len(args) > len(names)
            or any(name not in names[len(args) :] for name in kwargs)
            or len(args) + len(kwargs) != len(names)
        ):
            _fail()
        return super().__call__(*args, **kwargs)


class _Record(metaclass=_RecordType):
    __slots__ = ()

    def __post_init__(self):
        cls = type(self)
        if cls not in _RECORD_TYPES or any(
            not _matches(getattr(self, f.name), _hints(cls)[f.name])
            for f in fields(cls)
        ):
            _fail()
        self._validate()

    def _validate(self):
        pass

    def __repr__(self):
        return type(self).__name__ + "()"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class RequestId(_Record):
    value: str

    def _validate(self):
        if (
            re.fullmatch(
                r"rq1_[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}_"
                r"[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}",
                self.value,
            )
            is None
        ):
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class CommandRuntimeRow(_Record):
    projection_id: ProjectionId
    binding_guard: Revision
    control_revision: Revision
    owner_run_id: LocalId | None
    shutdown_phase: ShutdownPhase
    shutdown_operation_id: LocalId | None
    shutdown_owner_run_id: LocalId | None

    def _validate(self):
        idle = self.shutdown_phase is ShutdownPhase.IDLE
        if self.binding_guard.value < 1 or (
            (self.shutdown_operation_id is None) != idle
            or (self.shutdown_owner_run_id is None) != idle
            or (not idle and self.owner_run_id is None)
        ):
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class OperationRow(_Record):
    projection_id: ProjectionId
    operation_id: LocalId
    request_namespace: LocalId
    request_nonce: LocalId
    command: LocalCommandKind
    payload_version: Literal[1]
    digest_version: Literal[1]
    digest: Sha256Hex
    state: OperationState
    revision: Revision
    accepted_at: Timestamp
    updated_at: Timestamp
    completed_at: Timestamp | None
    code: ErrorCode | None
    effect_completed: bool
    expected_binding_revision: Revision
    expected_config_revision: Revision
    expected_preview_id: LocalId | None
    confirmation_yes: bool
    duplicate_risk_acknowledged: bool

    def _validate(self):
        terminal = self.state in {OperationState.COMPLETED, OperationState.REJECTED}
        preview_command = self.command is LocalCommandKind.BACKFILL_PREVIEW
        start_command = self.command is LocalCommandKind.BACKFILL_START
        if (
            self.revision.value < 1
            or (self.completed_at is not None) != terminal
            or self.updated_at.value < self.accepted_at.value
            or (
                self.completed_at is not None
                and not self.accepted_at.value
                <= self.completed_at.value
                <= self.updated_at.value
            )
            or (self.effect_completed and self.state is not OperationState.COMPLETED)
            or (
                self.state is OperationState.REJECTED
                and (self.code is None or self.effect_completed)
            )
            or (
                self.state in {OperationState.ACCEPTED, OperationState.EXECUTING}
                and self.code is not None
            )
            or (preview_command and self.expected_preview_id is not None)
            or (start_command and self.expected_preview_id is None)
            or (
                not preview_command
                and not start_command
                and self.expected_preview_id is not None
            )
            or (not preview_command and not self.confirmation_yes)
            or (preview_command and self.confirmation_yes)
            or self.duplicate_risk_acknowledged
        ):
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class ControlPayloadRow(_Record):
    projection_id: ProjectionId
    operation_id: LocalId
    before_paused: bool
    after_paused: bool
    before_control_revision: Revision
    after_control_revision: Revision

    def _validate(self):
        if self.after_control_revision.value not in {
            self.before_control_revision.value,
            self.before_control_revision.value + 1,
        }:
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class BootstrapPayloadRow(_Record):
    projection_id: ProjectionId
    operation_id: LocalId
    config_semantic_digest: Sha256Hex
    config_artifact_digest: Sha256Hex
    bootstrap_request_id: RequestId
    initialized_schema_version: Count | None

    def _validate(self):
        if (
            self.initialized_schema_version is not None
            and self.initialized_schema_version.value < 1
        ):
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class AuthPayloadRow(_Record):
    projection_id: ProjectionId
    operation_id: LocalId
    role: Role
    expected_credential_revision: Revision
    expected_role_binding_revision: Revision
    expected_policy_revision: Revision
    supersedes_change_id: LocalId | None


@dataclass(frozen=True, slots=True, repr=False)
class BackfillPayloadRow(_Record):
    projection_id: ProjectionId
    operation_id: LocalId
    purpose: PreviewPurpose
    preview_operation_id: LocalId | None
    ruleset_revision: Revision
    window_start: Timestamp
    window_end: Timestamp
    discovery_cutoff: Timestamp
    scope_digest: Sha256Hex
    expires_at: Timestamp
    invalidating_revision: Revision

    def _validate(self):
        if (
            self.purpose is not PreviewPurpose.START_BACKFILL
            or self.window_start.value >= self.window_end.value
            or self.discovery_cutoff.value <= self.window_start.value
            or self.discovery_cutoff.value >= self.window_end.value
            or self.expires_at.value < self.window_end.value
        ):
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class BackfillPreviewRequest(_Record):
    operation_id: LocalId
    request_nonce: LocalId
    window_start: Timestamp
    window_end: Timestamp
    discovery_cutoff: Timestamp
    scope_digest: Sha256Hex
    expires_at: Timestamp
    invalidating_revision: Revision
    accepted_at: Timestamp

    def _validate(self):
        if (
            self.window_start.value >= self.window_end.value
            or self.discovery_cutoff.value <= self.window_start.value
            or self.discovery_cutoff.value >= self.window_end.value
            or self.expires_at.value < self.window_end.value
            or self.expires_at.value > self.accepted_at.value + timedelta(minutes=15)
            or not _valid_backfill_window(
                self.window_start, self.window_end, self.accepted_at
            )
        ):
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class BackfillStartRequest(_Record):
    operation_id: LocalId
    request_nonce: LocalId
    preview_operation_id: LocalId
    epoch_id: LocalId
    fence_history_id: ProviderId
    fence_recorded_at: Timestamp
    accepted_at: Timestamp

    def _validate(self):
        if (
            not self.fence_history_id.value
            or self.accepted_at.value < self.fence_recorded_at.value
        ):
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class BootstrapOperationSeed(_Record):
    operation_id: LocalId
    namespace: LocalId
    nonce: LocalId
    command: BootstrapCommand
    digest_version: Literal[1]
    digest: Sha256Hex
    config_semantic_digest: Sha256Hex
    config_artifact_digest: Sha256Hex
    accepted_at: Timestamp
    completed_at: Timestamp
    expected_binding_revision: Revision
    expected_config_revision: Revision
    confirmation_yes: bool
    duplicate_risk_acknowledged: bool

    def _validate(self):
        if (
            self.expected_binding_revision.value != 0
            or self.expected_config_revision.value != 0
            or not self.confirmation_yes
            or self.duplicate_risk_acknowledged
            or self.completed_at.value < self.accepted_at.value
        ):
            _fail()


@dataclass(frozen=True, slots=True, repr=False)
class FreshCommandBootstrap(_Record):
    current: BootstrapOperationSeed
    prior_config: BootstrapOperationSeed | None

    def _validate(self):
        current, prior = self.current, self.prior_config
        BootstrapOperationSeed.__post_init__(current)
        if current.command is not BootstrapCommand.FACET_INIT:
            _fail()
        if prior is not None:
            BootstrapOperationSeed.__post_init__(prior)
            if (
                prior.command is not BootstrapCommand.CONFIG_INIT
                or prior.namespace != current.namespace
                or prior.nonce == current.nonce
                or prior.operation_id == current.operation_id
                or prior.config_semantic_digest != current.config_semantic_digest
                or prior.config_artifact_digest != current.config_artifact_digest
            ):
                _fail()


@dataclass(frozen=True, slots=True, repr=False)
class BootstrapInspection(_Record):
    schema_version: SchemaVersion
    owner: OwnerSessionInfo
    current_operation: OperationRow | None
    current_payload: BootstrapPayloadRow | None
    prior_operation: OperationRow | None
    prior_payload: BootstrapPayloadRow | None

    def _validate(self):
        if self.schema_version.value != 2:
            _fail()
        for operation, payload, command in (
            (self.current_operation, self.current_payload, LocalCommandKind.FACET_INIT),
            (self.prior_operation, self.prior_payload, LocalCommandKind.CONFIG_INIT),
        ):
            if (operation is None) != (payload is None):
                _fail()
            if operation is None:
                continue
            OperationRow.__post_init__(operation)
            BootstrapPayloadRow.__post_init__(payload)
            if (
                operation.command is not command
                or operation.state is not OperationState.COMPLETED
                or not operation.effect_completed
                or operation.code is not None
                or operation.request_namespace != self.owner.request_namespace
                or operation.projection_id != payload.projection_id
                or operation.operation_id != payload.operation_id
                or payload.bootstrap_request_id.value
                != (
                    f"rq1_{operation.request_namespace.value}_"
                    f"{operation.request_nonce.value}"
                )
                or (
                    command is LocalCommandKind.CONFIG_INIT
                    and payload.initialized_schema_version is not None
                )
                or (
                    command is LocalCommandKind.FACET_INIT
                    and payload.initialized_schema_version != Count(2)
                )
            ):
                _fail()
        if (
            self.current_operation is not None
            and self.prior_operation is not None
            and (
                self.current_operation.projection_id
                != self.prior_operation.projection_id
                or self.current_operation.request_nonce
                == self.prior_operation.request_nonce
                or self.current_operation.operation_id
                == self.prior_operation.operation_id
            )
        ):
            _fail()


_RECORD_TYPES = frozenset(
    (
        RequestId,
        CommandRuntimeRow,
        OperationRow,
        ControlPayloadRow,
        BootstrapPayloadRow,
        AuthPayloadRow,
        BackfillPayloadRow,
        BackfillPreviewRequest,
        BackfillStartRequest,
        BootstrapOperationSeed,
        FreshCommandBootstrap,
        BootstrapInspection,
    )
)
