"""Production CLI foundation, with sanitized errors and no implicit live calls."""

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from facet import __version__
from facet.config import ConfigError, dump_config, initial_template, load_config
from facet.contracts import ErrorCode, ProjectionId
from facet.private_paths import inspect_state_root, select_paths

from .config import config_read


class _InputError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's message can contain private paths/values or the entire argv.
        raise _InputError()


def _common(parser: _Parser) -> None:
    parser.set_defaults(_help_parser=parser)
    for flag, destination in [
        ("--config", "config_path"),
        ("--state-dir", "state_dir"),
        ("--projection", "projection"),
        ("--timeout", "timeout"),
    ]:
        parser.add_argument(flag, dest=destination, default=argparse.SUPPRESS)
    for flag in ["--json", "--private-metadata", "--public", "--version", "--help"]:
        parser.add_argument(flag, action="store_true", default=argparse.SUPPRESS)


def _mutations(parser: _Parser) -> None:
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--request-id")


def build_parser() -> _Parser:
    parser = _Parser(
        prog="facet",
        add_help=False,
        allow_abbrev=False,
        description=(
            "Facet private initialization and offline config reads. "
            "Run currently performs preflight only; OAuth and sync wiring pending."
        ),
    )
    _common(parser)
    commands = parser.add_subparsers(dest="family", parser_class=_Parser)
    init = commands.add_parser(
        "init",
        add_help=False,
        allow_abbrev=False,
        help="initialize one private Facet projection state",
    )
    _common(init)
    _mutations(init)
    init.add_argument("--source")
    init.add_argument("--target")
    config = commands.add_parser(
        "config",
        add_help=False,
        allow_abbrev=False,
        help="strict structural config reads",
    )
    _common(config)
    actions = config.add_subparsers(dest="action", parser_class=_Parser)
    descriptions = {
        "validate": "Validate standalone config structure only; binding/state pending.",
        "show": "Show a standalone config summary; private metadata requires opt-in.",
        "init": "Unavailable until single-owner init integration; creates no files.",
        "apply": "Unavailable until single-owner execution; no config read/write.",
    }
    for name, description in descriptions.items():
        command = actions.add_parser(
            name,
            add_help=False,
            allow_abbrev=False,
            help=description,
            description=description,
        )
        _common(command)
        if name in {"init", "apply"}:
            _mutations(command)
        if name == "init":
            command.add_argument("--source")
            command.add_argument("--target")
        if name == "apply":
            command.add_argument("--file", help="planned operational-change input")
    run = commands.add_parser(
        "run",
        add_help=False,
        allow_abbrev=False,
        help="check foreground prerequisites; sync service wiring pending",
    )
    _common(run)
    run.add_argument("--once", action="store_true")
    return parser


def _write_config(path: Path, raw: bytes) -> None:
    """Publish a newly-created private config without following links."""
    parent = path.parent
    info = parent.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o77
    ):
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if (
            not stat.S_ISREG(existing.st_mode)
            or existing.st_uid != os.geteuid()
            or stat.S_IMODE(existing.st_mode) & 0o77
            or existing.st_nlink != 1
        ):
            raise ConfigError(ErrorCode.SCOPE_REQUIRED)
        try:
            if _read_managed_config(path) == raw:
                _sync_directory(parent)
                return
        except ConfigError:
            raise
        except OSError:
            raise ConfigError(ErrorCode.PERSISTENCE_FAILURE) from None
        raise ConfigError(ErrorCode.REQUEST_CONFLICT)
    temporary = parent / (".config-" + uuid4().hex + ".pending")
    descriptor = None
    created = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        created = True
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written == 0:
                raise OSError()
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        # link is atomic and fails if another file already occupies config.yaml.
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        created = False
        _sync_directory(parent)
    except FileExistsError:
        raise ConfigError(ErrorCode.OWNER_BUSY) from None
    except OSError:
        raise ConfigError(ErrorCode.PERSISTENCE_FAILURE) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            with suppress(OSError):
                temporary.unlink()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_managed_config(path: Path) -> bytes:
    try:
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        )
    except OSError:
        raise ConfigError(ErrorCode.OWNER_UNAVAILABLE) from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o77
            or info.st_nlink != 1
            or info.st_size > 1024 * 1024
        ):
            raise ConfigError(ErrorCode.SCOPE_REQUIRED)
        chunks = []
        remaining = info.st_size + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except OSError:
        raise ConfigError(ErrorCode.PERSISTENCE_FAILURE) from None
    finally:
        os.close(descriptor)
    if len(raw) != info.st_size or len(raw) > 1024 * 1024:
        raise ConfigError(ErrorCode.OWNER_BUSY)
    return raw


def _init_command(options: object) -> tuple[dict, tuple[str, ...]]:
    if getattr(options, "config_path", None) is not None:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    if getattr(options, "public", False):
        raise ConfigError(ErrorCode.SCOPE_REQUIRED)
    if not getattr(options, "yes", False):
        raise ConfigError(ErrorCode.CONFIRMATION_REQUIRED)
    request_id = getattr(options, "request_id", None)
    if request_id is None:
        raise ConfigError(ErrorCode.CONFIRMATION_REQUIRED)
    from facet.db.command_records import RequestId
    from facet.runtime.state_owner import StateOwner
    try:
        RequestId(request_id)
        config = initial_template(
            options.source,
            options.target,
            getattr(options, "projection", None) or "gmail-default",
        )
        raw = dump_config(config)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    paths = select_paths(getattr(options, "state_dir", None), None)
    if inspect_state_root(paths.root):
        with StateOwner.inspect_initialization(
            paths.root, config.projection.id, request_id
        ) as inspection:
            payload = inspection.current_payload
            if (
                payload is None
                or payload.config_artifact_digest.value
                != hashlib.sha256(raw).hexdigest()
            ):
                raise ConfigError(ErrorCode.REQUEST_CONFLICT)
            _write_config(paths.config, raw)
        data = {
            "state_initialized": True,
            "binding_state": "verification_pending",
            "replayed": True,
        }
    else:
        owner = StateOwner.create(paths.root, config, raw, request_id=request_id)
        try:
            _write_config(paths.config, raw)
        finally:
            owner.close()
        data = {
            "state_initialized": True,
            "binding_state": "verification_pending",
            "replayed": False,
        }
    if getattr(options, "private_metadata", False):
        data["private_metadata"] = {
            "projection": config.projection.id.value,
            "source_email": config.projection.source_email,
            "target_email": config.projection.target_email,
            "state_dir": str(paths.root),
            "config": str(paths.config),
        }
    return data, ("binding_verification_pending",)


def _run_preflight(options: object) -> tuple[dict, tuple[str, ...]]:
    from facet.runtime.state_owner import StateOwner

    paths = select_paths(
        getattr(options, "state_dir", None), getattr(options, "config_path", None)
    )
    if getattr(options, "config_path", None) is not None:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    raw = _read_managed_config(paths.config)
    config = load_config(raw)
    if (
        getattr(options, "projection", None) is not None
        and ProjectionId(options.projection) != config.projection.id
    ):
        raise ConfigError(ErrorCode.BINDING_MISMATCH)
    owner = StateOwner.open(paths.root, config)
    try:
        bindings = owner.bindings()
        if any(
            binding is None or binding.state.value != "verified"
            for binding in bindings.values()
        ):
            raise ConfigError(ErrorCode.BINDING_PENDING)
        raise ConfigError(ErrorCode.SOURCE_AUTH_REQUIRED)
    finally:
        owner.close()


def _check_arguments(argv: list[str]) -> None:
    selectors = {"--config", "--state-dir", "--projection", "--timeout"}
    seen = set()
    for item in argv:
        flag = item.split("=", 1)[0]
        if flag in selectors:
            if flag in seen:
                raise _InputError()
            seen.add(flag)


def _emit(
    command: str,
    *,
    code: ErrorCode | None = None,
    data: dict | None = None,
    warnings: tuple[str, ...] = (),
    json_mode: bool = False,
) -> int:
    exits = {
        ErrorCode.INVALID_INPUT: 2,
        ErrorCode.CONFIRMATION_REQUIRED: 2,
        ErrorCode.REQUEST_CONFLICT: 3,
        ErrorCode.BINDING_MISMATCH: 3,
        ErrorCode.BINDING_PENDING: 3,
        ErrorCode.SCOPE_REQUIRED: 3,
        ErrorCode.SOURCE_AUTH_REQUIRED: 3,
        ErrorCode.TARGET_AUTH_REQUIRED: 3,
        ErrorCode.OWNER_UNAVAILABLE: 4,
        ErrorCode.OWNER_BUSY: 4,
        ErrorCode.MAINTENANCE_INCOMPLETE: 4,
    }
    exit_code = exits.get(code, 7 if code else 0)
    result = {
        "schema_version": 1,
        "command": command,
        "status": "completed" if code is None else "blocked",
        "code": code.value if code else None,
        "data": data or {},
        "warnings": list(warnings),
    }
    if json_mode:
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    elif code:
        print(f"facet: {code.value}", file=sys.stderr)
    elif command == "help":
        print(result["data"]["help"], end="")
    elif command == "version":
        print(__version__)
    else:
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return exit_code


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in arguments
    command = "cli"
    try:
        _check_arguments(arguments)
        parser = build_parser()
        options = parser.parse_args(arguments)
        if getattr(options, "help", False):
            return _emit(
                "help",
                data={"help": options._help_parser.format_help()},
                json_mode=json_mode,
            )
        if getattr(options, "version", False):
            return _emit("version", data={"version": __version__}, json_mode=json_mode)
        if getattr(options, "private_metadata", False) and getattr(
            options, "public", False
        ):
            raise _InputError()
        if hasattr(options, "projection"):
            ProjectionId(options.projection)
        if hasattr(options, "timeout"):
            timeout = float(options.timeout)
            if not math.isfinite(timeout) or timeout <= 0:
                raise _InputError()
        if options.family == "init":
            command = "init"
            data, warnings = _init_command(options)
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family == "run":
            command = "run"
            if not getattr(options, "once", False):
                raise _InputError()
            data, warnings = _run_preflight(options)
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family != "config" or options.action is None:
            raise _InputError()
        command = f"config.{options.action}"
        if options.action in {"init", "apply"}:
            raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
        data, warnings = config_read(options, show=options.action == "show")
        return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
    except ConfigError as error:
        return _emit(command, code=error.code, json_mode=json_mode)
    except (_InputError, ValueError, TypeError, UnicodeError):
        return _emit(command, code=ErrorCode.INVALID_INPUT, json_mode=json_mode)
    except OSError:
        return _emit(command, code=ErrorCode.PERSISTENCE_FAILURE, json_mode=json_mode)
    except Exception as error:
        code = getattr(error, "code", ErrorCode.PERSISTENCE_FAILURE)
        if type(code) is not ErrorCode:
            code = ErrorCode.PERSISTENCE_FAILURE
        return _emit(command, code=code, json_mode=json_mode)
