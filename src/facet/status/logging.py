"""Explicit production-only containment and a separate closed stderr writer.

This is not a sandbox for arbitrary Python/fd writes. Runtime owns admission,
transport debug checks, async hook registration and controlled failure shutdown.
No policy is installed merely by importing this module.
"""

import http.client
import logging
import logging.handlers
import os
import sys
import threading
import warnings
import weakref
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import ModuleType

from facet.contracts import ErrorCode, Role, Sha256Hex, Timestamp
from facet.gmail.retry import ProviderReason, ProviderStage

from .errors import OutputBoundaryError, catalog_entry
from .models import Component, PublicCount, _count, _exact, _require, _timestamp
from .serialization import _encode, _time


class LogEventKind(StrEnum):
    LIFECYCLE = "lifecycle"
    DEPENDENCY_STATE = "dependency_state"
    WORK_SUMMARY = "work_summary"
    BOUNDARY_FAILURE = "boundary_failure"


class SafeLogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class OperationStage(StrEnum):
    START = "start"
    RECOVERY = "recovery"
    DISCOVERY = "discovery"
    HISTORY = "history"
    PROJECTION = "projection"
    TARGET_INVENTORY = "target_inventory"
    COMPLETE = "complete"
    STOP = "stop"


@dataclass(frozen=True, slots=True, repr=False)
class SafeLogEvent:
    kind: LogEventKind
    level: SafeLogLevel
    at: Timestamp
    component: Component
    role: Role | None
    code: ErrorCode | None
    count: PublicCount | None
    stage: OperationStage | None = None
    provider_stage: ProviderStage | None = None
    reason: ProviderReason | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None
    elapsed_ms: int | None = None
    raw_digest: Sha256Hex | None = None

    def __post_init__(self):
        _exact(self, SafeLogEvent)
        _exact(self.kind, LogEventKind)
        _exact(self.level, SafeLogLevel)
        _timestamp(self.at)
        _exact(self.component, Component)
        _exact(self.role, Role, nullable=True)
        _exact(self.code, ErrorCode, nullable=True)
        _count(self.count, nullable=True)
        _exact(self.stage, OperationStage, nullable=True)
        _exact(self.provider_stage, ProviderStage, nullable=True)
        _exact(self.reason, ProviderReason, nullable=True)
        _exact(self.raw_digest, Sha256Hex, nullable=True)
        for value in (self.retry_after_seconds, self.elapsed_ms):
            _count(value, nullable=True)
        _require(
            self.http_status is None
            or (type(self.http_status) is int and 100 <= self.http_status <= 599)
        )
        if self.raw_digest is not None:
            Sha256Hex.__post_init__(self.raw_digest)
        required_role = {
            Component.SOURCE: Role.SOURCE,
            Component.TARGET: Role.TARGET,
        }.get(self.component)
        _require(self.role is required_role)
        if self.kind in (LogEventKind.BOUNDARY_FAILURE, LogEventKind.DEPENDENCY_STATE):
            _require(self.code is not None and self.count is None)
        elif self.kind is LogEventKind.WORK_SUMMARY:
            _require(self.count is not None and self.code is None)
        else:
            _require(self.code is None and self.count is None)


_WRITE_LOCK = threading.Lock()
_CONFIGURED = False
_FAILED = False
_LOGGING_UNAVAILABLE = False
_DROP = None
_FIXED_FAILURE = b"facet: consistency_failure\n"
_STANDARD_HANDLER_TYPES = (
    logging.NullHandler,
    logging.StreamHandler,
    logging.FileHandler,
    logging.handlers.BufferingHandler,
    logging.handlers.MemoryHandler,
)


def _write(payload: bytes) -> None:
    global _LOGGING_UNAVAILABLE
    with _WRITE_LOCK:
        try:
            # max4096 keeps a normal pipe write bounded and atomic; no formatter.
            # A short/failed sink is failure, never a recursive raw error report.
            if os.write(2, payload) != len(payload):
                _LOGGING_UNAVAILABLE = True
        except OSError:
            _LOGGING_UNAVAILABLE = True


def emit_safe(event: SafeLogEvent) -> None:
    try:
        _exact(event, SafeLogEvent)
        SafeLogEvent.__post_init__(event)
        entry = None if event.code is None else catalog_entry(event.code)
        result = {
            "kind": event.kind.value,
            "level": event.level.value,
            "at": _time(event.at),
            "component": event.component.value,
            "role": None if event.role is None else event.role.value,
            "code": None if event.code is None else event.code.value,
            "count": event.count,
            "error_class": None if entry is None else entry.error_class.value,
        }
        # Optional operational fields are local logs, never public DTO fields.
        for name in (
            "stage",
            "provider_stage",
            "reason",
            "http_status",
            "retry_after_seconds",
            "elapsed_ms",
            "raw_digest",
        ):
            value = getattr(event, name)
            if value is not None:
                result[name] = value.value if hasattr(value, "value") else value
        payload = (_encode(result) + "\n").encode("ascii")
        _require(len(payload) <= 4096)
    except (OutputBoundaryError, AttributeError, ValueError, TypeError):
        _write(_FIXED_FAILURE)
        return
    _write(payload)


def emit_operation(stage, *, code=None, count=None, elapsed_ms=None, raw_digest=None):
    emit_safe(
        SafeLogEvent(
            LogEventKind.BOUNDARY_FAILURE
            if code
            else LogEventKind.WORK_SUMMARY
            if count is not None
            else LogEventKind.LIFECYCLE,
            SafeLogLevel.WARNING if code else SafeLogLevel.INFO,
            Timestamp(datetime.now(UTC)),
            Component.RUNTIME,
            None,
            code,
            count,
            stage=stage,
            elapsed_ms=elapsed_ms,
            raw_digest=raw_digest,
        )
    )


def emit_provider_failure(error):
    emit_safe(
        SafeLogEvent(
            LogEventKind.BOUNDARY_FAILURE,
            SafeLogLevel.WARNING,
            Timestamp(datetime.now(UTC)),
            Component.SOURCE if error.role is Role.SOURCE else Component.TARGET,
            error.role,
            error.code,
            None,
            provider_stage=error.provider_stage,
            reason=error.reason,
            http_status=error.status,
            retry_after_seconds=error.retry_after_seconds,
        )
    )


def _warning(message, category, filename, lineno, file=None, line=None):
    _write(_FIXED_FAILURE)


def _uncaught(exc_type, value, traceback):
    _write(_FIXED_FAILURE)
    # Raising SystemExit inside sys.excepthook invokes Python's hook-error printer.
    # The production process is already failing; exit without any raw formatter.
    os._exit(7)


def _thread_failure(args):
    global _FAILED
    _FAILED = True
    _write(_FIXED_FAILURE)


def _unraisable(args):
    global _FAILED
    _FAILED = True
    _write(_FIXED_FAILURE)


def sealed_asyncio_exception_handler(loop, context):
    """M1-03 must register this before actual task admission; no context reads."""
    global _FAILED
    _FAILED = True
    _write(_FIXED_FAILURE)


def _discard_handlers() -> bool:
    """Drop pending records BEFORE refusal or shutdown; never call handler.close.

    Removing logger handlers alone leaves weak references used by logging.shutdown.
    We deliberately retire that stdlib registry while startup is single-threaded.
    Unsupported custom implementations cause refusal, not calls into their hooks.
    External custom atexit code is outside the supported process contract.
    """
    supported = True
    loggers = []
    if type(logging.root) is logging.RootLogger:
        loggers.append(logging.root)
    else:
        supported = False
    manager = logging.Logger.manager
    if type(manager) is logging.Manager and type(manager.loggerDict) is dict:
        candidates = tuple(manager.loggerDict.values())
        # logging.disable calls Manager._clear_cache and traverses custom Logger
        # attributes before it returns. Set only the exact stdlib manager's
        # threshold here; clear only exact known logger caches below.
        manager.disable = sys.maxsize
    else:
        candidates = ()
        supported = False
    for logger in candidates:
        if type(logger) is logging.PlaceHolder:
            continue
        if type(logger) is not logging.Logger:
            supported = False
        else:
            loggers.append(logger)
    handlers = []
    for ref in tuple(logging._handlerList):
        if type(ref) is not weakref.ReferenceType:
            supported = False
            continue
        handler = ref()
        if handler is not None:
            handlers.append(handler)
    for logger in loggers:
        if type(logger.handlers) is list:
            handlers.extend(logger.handlers)
        else:
            supported = False
        logger.handlers = []
        if type(logger._cache) is dict:
            logger._cache.clear()
        else:
            supported = False
    if logging.lastResort is not None:
        handlers.append(logging.lastResort)
    # Retire shutdown references before examining supported instances. Unknown
    # implementations are not inspected, formatted, flushed or closed at all.
    logging._handlerList.clear()
    logging._handlers.clear()
    for handler in handlers:
        cls = type(handler)
        if (
            not any(cls is allowed for allowed in _STANDARD_HANDLER_TYPES)
            and cls is not logging._StderrHandler
        ):
            supported = False
            continue
        # Do not invoke a custom method/property, even on a rejected handler.
        try:
            state = object.__getattribute__(handler, "__dict__")
        except AttributeError:
            supported = False
            continue
        formatter = state.get("formatter")
        if formatter is not None and type(formatter) is not logging.Formatter:
            supported = False
        if "buffer" in state:
            state["buffer"] = []
        if "target" in state:
            state["target"] = None
    return supported


def _debug_disabled() -> bool:
    level = http.client.HTTPConnection.debuglevel
    if type(level) is not int or level != 0:
        return False
    module = sys.modules.get("httplib2")
    if module is not None:
        if type(module) is not ModuleType:
            return False
        level = vars(module).get("debuglevel", 0)
        if type(level) is not int or level != 0:
            return False
    return not (sys.flags.dev_mode or sys.flags.verbose)


def _policy_intact() -> bool:
    # Type checks must precede property/attribute access and equality. Even
    # object.__getattribute__ executes a descriptor on an unsupported subclass.
    manager = logging.Logger.manager
    if (
        type(logging.root) is not logging.RootLogger
        or type(manager) is not logging.Manager
    ):
        return False
    if type(manager.loggerDict) is not dict or type(manager.disable) is not int:
        return False
    if type(logging.root.handlers) is not list:
        return False
    if (
        _FAILED
        or _LOGGING_UNAVAILABLE
        or manager.disable != sys.maxsize
        or logging.raiseExceptions is not False
        or logging.getLoggerClass() is not logging.Logger
        or logging.getLogRecordFactory() is not logging.LogRecord
        or len(logging.root.handlers) != 1
        or logging.root.handlers[0] is not _DROP
        or logging.lastResort is not _DROP
        or warnings.showwarning is not _warning
        or sys.excepthook is not _uncaught
        or threading.excepthook is not _thread_failure
        or sys.unraisablehook is not _unraisable
        or not _debug_disabled()
    ):
        return False
    for logger in tuple(manager.loggerDict.values()):
        if type(logger) is logging.PlaceHolder:
            continue
        if type(logger) is not logging.Logger:
            return False
        if type(logger.handlers) is not list or logger.handlers:
            return False
    for ref in logging._handlerList:
        if type(ref) is not weakref.ReferenceType:
            return False
        if ref() is not None and ref() is not _DROP:
            return False
    return True


def configure_production_logging() -> None:
    global _CONFIGURED, _FAILED, _DROP
    hooks_intact = (
        warnings.showwarning is _warning
        and sys.excepthook is _uncaught
        and threading.excepthook is _thread_failure
        and sys.unraisablehook is _unraisable
    )
    # Install sealed failure hooks BEFORE any logging operation. They are not
    # permission to inspect a foreign object; such objects are rejected untouched.
    warnings.showwarning = _warning
    sys.excepthook = _uncaught
    threading.excepthook = _thread_failure
    sys.unraisablehook = _unraisable
    if _CONFIGURED:
        if hooks_intact and _policy_intact():
            return
        _FAILED = True
        _discard_handlers()
        raise OutputBoundaryError()
    # Even refusal must discard a previously buffered record before atexit.
    logging.raiseExceptions = False
    supported = _discard_handlers()
    supported = supported and (
        type(logging.root) is logging.RootLogger
        and logging.getLoggerClass() is logging.Logger
        and logging.getLogRecordFactory() is logging.LogRecord
        and _debug_disabled()
    )
    _DROP = logging.NullHandler()
    if type(logging.root) is logging.RootLogger:
        logging.root.handlers = [_DROP]
    logging.lastResort = _DROP
    if not supported or _FAILED:
        _FAILED = True
        raise OutputBoundaryError()
    _CONFIGURED = True
