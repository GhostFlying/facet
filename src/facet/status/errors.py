"""Closed presentation catalogue; no provider exception inspection."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from facet.contracts import ErrorClass, ErrorCode


class OutputBoundaryError(ValueError):
    """A sealed failure that never retains the rejected object."""

    code = ErrorCode.CONSISTENCY_FAILURE

    def __init__(self):
        super().__init__("consistency_failure")

    def __repr__(self):
        return "OutputBoundaryError('consistency_failure')"


class Suggestion(StrEnum):
    CORRECT_INPUT = "correct_input"
    INSPECT_REQUEST = "inspect_request"
    REPEAT_SAME_REQUEST = "repeat_same_request"
    CONFIRM_SCOPE = "confirm_scope"
    VERIFY_BINDING = "verify_binding"
    REFRESH_PREVIEW = "refresh_preview"
    INSPECT_OWNER = "inspect_owner"
    WAIT_RECEIPT = "wait_receipt"
    AUTHORIZE_SOURCE = "authorize_source"
    AUTHORIZE_TARGET = "authorize_target"
    WAIT_DEPENDENCY = "wait_dependency"
    INSPECT_TARGET_STORAGE = "inspect_target_storage"
    INSPECT_RECOVERY = "inspect_recovery"
    INSPECT_WORK = "inspect_work"
    INSPECT_MAINTENANCE = "inspect_maintenance"


_SUGGESTIONS = MappingProxyType(
    {
        Suggestion.CORRECT_INPUT: "Correct the local input and run validation.",
        Suggestion.INSPECT_REQUEST: (
            "Inspect the existing request before submitting "
            "work."
        ),
        Suggestion.REPEAT_SAME_REQUEST: (
            "Resubmit only the confirmed unaccepted request with its "
            "original key and payload."
        ),
        Suggestion.CONFIRM_SCOPE: (
            "Review the selected scope and provide the required "
            "confirmation."
        ),
        Suggestion.VERIFY_BINDING: (
            "Verify the configured account roles without changing "
            "the binding."
        ),
        Suggestion.REFRESH_PREVIEW: "Create a fresh scoped preview before continuing.",
        Suggestion.INSPECT_OWNER: (
            "Inspect the owner state; do not start a second "
            "writer."
        ),
        Suggestion.WAIT_RECEIPT: (
            "Look up the retained request receipt before taking "
            "further action."
        ),
        Suggestion.AUTHORIZE_SOURCE: "Reauthorize Source on the deployment host.",
        Suggestion.AUTHORIZE_TARGET: "Reauthorize Target on the deployment host.",
        Suggestion.WAIT_DEPENDENCY: (
            "Retain queued work and wait for the dependency to "
            "recover."
        ),
        Suggestion.INSPECT_TARGET_STORAGE: (
            "Inspect Target storage without deleting mailbox "
            "data."
        ),
        Suggestion.INSPECT_RECOVERY: (
            "Inspect recovery evidence; do not blindly repeat an "
            "insert."
        ),
        Suggestion.INSPECT_WORK: (
            "Inspect the selected work through the scoped local "
            "CLI."
        ),
        Suggestion.INSPECT_MAINTENANCE: (
            "Stop affected writes and use offline maintenance; do "
            "not initialize an empty database."
        ),
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class CatalogEntry:
    code: ErrorCode
    error_class: ErrorClass
    message: str
    suggestion: Suggestion
    failure_exit: Literal[2, 3, 4, 5, 6, 7]
    automatic_dependency_retry: bool


_CATALOG = MappingProxyType(
    {
        ErrorCode.INVALID_INPUT: CatalogEntry(
            ErrorCode.INVALID_INPUT,
            ErrorClass.INPUT,
            "Input is invalid.",
            Suggestion.CORRECT_INPUT,
            2,
            False,
        ),
        ErrorCode.UNSUPPORTED_VERSION: CatalogEntry(
            ErrorCode.UNSUPPORTED_VERSION,
            ErrorClass.INPUT,
            "This version is not supported.",
            Suggestion.CORRECT_INPUT,
            2,
            False,
        ),
        ErrorCode.REQUEST_CONFLICT: CatalogEntry(
            ErrorCode.REQUEST_CONFLICT,
            ErrorClass.GUARD,
            "The request key conflicts with existing work.",
            Suggestion.INSPECT_REQUEST,
            3,
            False,
        ),
        ErrorCode.REQUEST_NOT_RECEIVED: CatalogEntry(
            ErrorCode.REQUEST_NOT_RECEIVED,
            ErrorClass.OWNERSHIP,
            "The owner confirmed that the request was not accepted.",
            Suggestion.REPEAT_SAME_REQUEST,
            4,
            False,
        ),
        ErrorCode.REQUEST_OUTCOME_UNKNOWN: CatalogEntry(
            ErrorCode.REQUEST_OUTCOME_UNKNOWN,
            ErrorClass.ATTENTION,
            "The request outcome is unknown.",
            Suggestion.INSPECT_REQUEST,
            6,
            False,
        ),
        ErrorCode.REQUEST_LINEAGE_MISMATCH: CatalogEntry(
            ErrorCode.REQUEST_LINEAGE_MISMATCH,
            ErrorClass.GUARD,
            "The request belongs to a different restored lineage.",
            Suggestion.INSPECT_REQUEST,
            3,
            False,
        ),
        ErrorCode.CONFIRMATION_REQUIRED: CatalogEntry(
            ErrorCode.CONFIRMATION_REQUIRED,
            ErrorClass.GUARD,
            "Explicit confirmation is required.",
            Suggestion.CONFIRM_SCOPE,
            3,
            False,
        ),
        ErrorCode.SCOPE_REQUIRED: CatalogEntry(
            ErrorCode.SCOPE_REQUIRED,
            ErrorClass.GUARD,
            "The required approved scope is unavailable.",
            Suggestion.CONFIRM_SCOPE,
            3,
            False,
        ),
        ErrorCode.BINDING_MISMATCH: CatalogEntry(
            ErrorCode.BINDING_MISMATCH,
            ErrorClass.GUARD,
            "Account binding verification failed.",
            Suggestion.VERIFY_BINDING,
            3,
            False,
        ),
        ErrorCode.BINDING_PENDING: CatalogEntry(
            ErrorCode.BINDING_PENDING,
            ErrorClass.GUARD,
            "Account binding verification is pending.",
            Suggestion.VERIFY_BINDING,
            3,
            False,
        ),
        ErrorCode.PREVIEW_INVALID: CatalogEntry(
            ErrorCode.PREVIEW_INVALID,
            ErrorClass.GUARD,
            "The selected preview is no longer valid.",
            Suggestion.REFRESH_PREVIEW,
            3,
            False,
        ),
        ErrorCode.GENERATION_STALE: CatalogEntry(
            ErrorCode.GENERATION_STALE,
            ErrorClass.GUARD,
            "The selected work generation is stale.",
            Suggestion.REFRESH_PREVIEW,
            3,
            False,
        ),
        ErrorCode.OWNER_UNAVAILABLE: CatalogEntry(
            ErrorCode.OWNER_UNAVAILABLE,
            ErrorClass.OWNERSHIP,
            "The required owner is unavailable.",
            Suggestion.INSPECT_OWNER,
            4,
            False,
        ),
        ErrorCode.OWNER_BUSY: CatalogEntry(
            ErrorCode.OWNER_BUSY,
            ErrorClass.OWNERSHIP,
            "The owner is busy.",
            Suggestion.INSPECT_OWNER,
            4,
            False,
        ),
        ErrorCode.MAINTENANCE_INCOMPLETE: CatalogEntry(
            ErrorCode.MAINTENANCE_INCOMPLETE,
            ErrorClass.OWNERSHIP,
            "Maintenance has not completed.",
            Suggestion.INSPECT_MAINTENANCE,
            4,
            False,
        ),
        ErrorCode.WAIT_TIMEOUT: CatalogEntry(
            ErrorCode.WAIT_TIMEOUT,
            ErrorClass.OWNERSHIP,
            "The bounded wait ended before completion.",
            Suggestion.WAIT_RECEIPT,
            4,
            False,
        ),
        ErrorCode.SOURCE_AUTH_REQUIRED: CatalogEntry(
            ErrorCode.SOURCE_AUTH_REQUIRED,
            ErrorClass.DEPENDENCY,
            "Source authorization is required.",
            Suggestion.AUTHORIZE_SOURCE,
            5,
            False,
        ),
        ErrorCode.TARGET_AUTH_REQUIRED: CatalogEntry(
            ErrorCode.TARGET_AUTH_REQUIRED,
            ErrorClass.DEPENDENCY,
            "Target authorization is required.",
            Suggestion.AUTHORIZE_TARGET,
            5,
            False,
        ),
        ErrorCode.SOURCE_RATE_LIMITED: CatalogEntry(
            ErrorCode.SOURCE_RATE_LIMITED,
            ErrorClass.DEPENDENCY,
            "Source rate limiting is active.",
            Suggestion.WAIT_DEPENDENCY,
            5,
            True,
        ),
        ErrorCode.TARGET_RATE_LIMITED: CatalogEntry(
            ErrorCode.TARGET_RATE_LIMITED,
            ErrorClass.DEPENDENCY,
            "Target rate limiting is active.",
            Suggestion.WAIT_DEPENDENCY,
            5,
            True,
        ),
        ErrorCode.NETWORK_UNAVAILABLE: CatalogEntry(
            ErrorCode.NETWORK_UNAVAILABLE,
            ErrorClass.DEPENDENCY,
            "A network dependency is unavailable.",
            Suggestion.WAIT_DEPENDENCY,
            5,
            True,
        ),
        ErrorCode.TARGET_STORAGE_FULL: CatalogEntry(
            ErrorCode.TARGET_STORAGE_FULL,
            ErrorClass.DEPENDENCY,
            "Target storage is full.",
            Suggestion.INSPECT_TARGET_STORAGE,
            5,
            False,
        ),
        ErrorCode.INSERT_RESULT_UNKNOWN: CatalogEntry(
            ErrorCode.INSERT_RESULT_UNKNOWN,
            ErrorClass.ATTENTION,
            "The insert outcome is unknown.",
            Suggestion.INSPECT_RECOVERY,
            6,
            False,
        ),
        ErrorCode.DUPLICATE_CANDIDATES: CatalogEntry(
            ErrorCode.DUPLICATE_CANDIDATES,
            ErrorClass.ATTENTION,
            "More than one recovery candidate exists.",
            Suggestion.INSPECT_RECOVERY,
            6,
            False,
        ),
        ErrorCode.ATTRIBUTION_UNKNOWN: CatalogEntry(
            ErrorCode.ATTRIBUTION_UNKNOWN,
            ErrorClass.ATTENTION,
            "Recovery attribution is unverified.",
            Suggestion.INSPECT_RECOVERY,
            6,
            False,
        ),
        ErrorCode.FIDELITY_MISMATCH: CatalogEntry(
            ErrorCode.FIDELITY_MISMATCH,
            ErrorClass.ATTENTION,
            "Message fidelity verification failed.",
            Suggestion.INSPECT_RECOVERY,
            6,
            False,
        ),
        ErrorCode.SOURCE_MISSING: CatalogEntry(
            ErrorCode.SOURCE_MISSING,
            ErrorClass.ATTENTION,
            "Required source data is missing.",
            Suggestion.INSPECT_WORK,
            6,
            False,
        ),
        ErrorCode.TARGET_MISSING: CatalogEntry(
            ErrorCode.TARGET_MISSING,
            ErrorClass.ATTENTION,
            "A managed target message is missing.",
            Suggestion.INSPECT_WORK,
            6,
            False,
        ),
        ErrorCode.DATABASE_UNAVAILABLE: CatalogEntry(
            ErrorCode.DATABASE_UNAVAILABLE,
            ErrorClass.PERSISTENCE,
            "The local database is unavailable.",
            Suggestion.INSPECT_MAINTENANCE,
            7,
            False,
        ),
        ErrorCode.PERSISTENCE_FAILURE: CatalogEntry(
            ErrorCode.PERSISTENCE_FAILURE,
            ErrorClass.PERSISTENCE,
            "Durable persistence failed.",
            Suggestion.INSPECT_MAINTENANCE,
            7,
            False,
        ),
        ErrorCode.CONSISTENCY_FAILURE: CatalogEntry(
            ErrorCode.CONSISTENCY_FAILURE,
            ErrorClass.PERSISTENCE,
            "A consistency check failed.",
            Suggestion.INSPECT_MAINTENANCE,
            7,
            False,
        ),
        ErrorCode.MAINTENANCE_REQUIRED: CatalogEntry(
            ErrorCode.MAINTENANCE_REQUIRED,
            ErrorClass.OWNERSHIP,
            "A supported maintenance step is required.",
            Suggestion.INSPECT_MAINTENANCE,
            4,
            False,
        ),
    }
)
assert set(_CATALOG) == set(ErrorCode)


def catalog_entry(code: ErrorCode) -> CatalogEntry:
    if type(code) is not ErrorCode:
        code = ErrorCode.CONSISTENCY_FAILURE
    return _CATALOG[code]


@dataclass(frozen=True, slots=True, repr=False)
class ErrorPresentation:
    code: ErrorCode
    error_class: ErrorClass
    message: str
    suggestion: Suggestion
    suggestion_text: str
    failure_exit: Literal[2, 3, 4, 5, 6, 7]

    def __post_init__(self):
        entry = catalog_entry(self.code)
        if (
            type(self.code) is not ErrorCode
            or self.error_class is not entry.error_class
            or type(self.message) is not str
            or self.message != entry.message
            or self.suggestion is not entry.suggestion
            or type(self.suggestion_text) is not str
            or self.suggestion_text != _SUGGESTIONS[entry.suggestion]
            or type(self.failure_exit) is not int
            or self.failure_exit != entry.failure_exit
        ):
            raise OutputBoundaryError()


def present_error(code: ErrorCode) -> ErrorPresentation:
    entry = catalog_entry(code)
    return ErrorPresentation(
        entry.code,
        entry.error_class,
        entry.message,
        entry.suggestion,
        _SUGGESTIONS[entry.suggestion],
        entry.failure_exit,
    )
