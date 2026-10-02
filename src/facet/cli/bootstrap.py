"""Production CLI foundation, with sanitized errors and no implicit live calls."""

import argparse
import json
import math
import sys

from facet import __version__
from facet.config import ConfigError
from facet.contracts import ErrorCode, ProjectionId

from .config import config_read


class _InputError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's message can contain private paths/values or the entire argv.
        raise _InputError()


def _common(parser: _Parser) -> None:
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
            "Facet production foundation: offline standalone config reads. "
            "Managed reads and mutations await the single-writer owner; "
            "no Gmail calls or backfill are started."
        ),
    )
    _common(parser)
    commands = parser.add_subparsers(dest="family", parser_class=_Parser)
    init = commands.add_parser(
        "init",
        add_help=False,
        allow_abbrev=False,
        help="unavailable until ownership/init integration",
    )
    _common(init)
    _mutations(init)
    config = commands.add_parser(
        "config",
        add_help=False,
        allow_abbrev=False,
        help="strict structural config reads",
    )
    _common(config)
    actions = config.add_subparsers(dest="action", parser_class=_Parser)
    for name in ["validate", "show", "init", "apply"]:
        command = actions.add_parser(name, add_help=False, allow_abbrev=False)
        _common(command)
        if name in {"init", "apply"}:
            _mutations(command)
        if name == "init":
            command.add_argument("--source")
            command.add_argument("--target")
        if name == "apply":
            command.add_argument("--set", action="append")
    return parser


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
        ErrorCode.BINDING_MISMATCH: 3,
        ErrorCode.SCOPE_REQUIRED: 3,
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
                "help", data={"help": parser.format_help()}, json_mode=json_mode
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
            raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
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
