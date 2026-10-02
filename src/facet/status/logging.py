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
from dataclasses import dataclass
from enum import StrEnum

from facet.contracts import ErrorCode, Role, Timestamp

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


@dataclass(frozen=True, slots=True, repr=False)
class SafeLogEvent:
    kind: LogEventKind
    level: SafeLogLevel
    at: Timestamp
    component: Component
    role: Role | None
    code: ErrorCode | None
    count: PublicCount | None

    def __post_init__(self):
        _exact(self, SafeLogEvent)
        _exact(self.kind, LogEventKind)
        _exact(self.level, SafeLogLevel)
        _timestamp(self.at)
        _exact(self.component, Component)
        _exact(self.role, Role, nullable=True)
        _exact(self.code, ErrorCode, nullable=True)
        _count(self.count, nullable=True)
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
        payload = (_encode(result) + "\n").encode("ascii")
        _require(len(payload) <= 4096)
    except (OutputBoundaryError, AttributeError):
        _write(_FIXED_FAILURE)
        return
    _write(payload)


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
    loggers = [logging.root]
    for logger in tuple(logging.Logger.manager.loggerDict.values()):
        if type(logger) is logging.PlaceHolder:
            continue
        if type(logger) is not logging.Logger:
            supported = False
        else:
            loggers.append(logger)
    handlers = []
    for ref in tuple(logging._handlerList):
        handler = ref()
        if handler is not None:
            handlers.append(handler)
    for logger in loggers:
        handlers.extend(logger.handlers)
        logger.handlers = []
    if logging.lastResort is not None:
        handlers.append(logging.lastResort)
    for handler in handlers:
        cls = type(handler)
        if (
            not any(cls is allowed for allowed in _STANDARD_HANDLER_TYPES)
            and cls is not logging._StderrHandler
        ):
            supported = False
        # Do not invoke a custom method/property, even on a rejected handler.
        try:
            state = object.__getattribute__(handler, "__dict__")
        except AttributeError:
            supported = False
            continue
        if "buffer" in state:
            state["buffer"] = []
        if "target" in state:
            state["target"] = None
    logging._handlerList.clear()
    logging._handlers.clear()
    return supported


def _debug_disabled() -> bool:
    if http.client.HTTPConnection.debuglevel != 0:
        return False
    module = sys.modules.get("httplib2")
    if module is not None and vars(module).get("debuglevel", 0) != 0:
        return False
    return not (sys.flags.dev_mode or sys.flags.verbose)


def _policy_intact() -> bool:
    if (
        _FAILED
        or _LOGGING_UNAVAILABLE
        or logging.root.manager.disable != sys.maxsize
        or logging.raiseExceptions is not False
        or logging.getLoggerClass() is not logging.Logger
        or logging.getLogRecordFactory() is not logging.LogRecord
        or type(logging.root) is not logging.RootLogger
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
    for logger in tuple(logging.Logger.manager.loggerDict.values()):
        if type(logger) is logging.PlaceHolder:
            continue
        if type(logger) is not logging.Logger or logger.handlers:
            return False
    return all(ref() is None or ref() is _DROP for ref in logging._handlerList)


def configure_production_logging() -> None:
    global _CONFIGURED, _FAILED, _DROP
    if _CONFIGURED:
        if _policy_intact():
            return
        _FAILED = True
        _discard_handlers()
        raise OutputBoundaryError()
    # Even refusal must discard a previously buffered record before atexit.
    logging.disable(sys.maxsize)
    logging.raiseExceptions = False
    supported = _discard_handlers()
    supported = supported and (
        type(logging.root) is logging.RootLogger
        and logging.getLoggerClass() is logging.Logger
        and logging.getLogRecordFactory() is logging.LogRecord
        and _debug_disabled()
    )
    _DROP = logging.NullHandler()
    logging.root.handlers = [_DROP]
    logging.lastResort = _DROP
    warnings.showwarning = _warning
    sys.excepthook = _uncaught
    threading.excepthook = _thread_failure
    sys.unraisablehook = _unraisable
    if not supported or _FAILED:
        _FAILED = True
        raise OutputBoundaryError()
    _CONFIGURED = True
