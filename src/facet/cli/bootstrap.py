"""Production CLI foundation, with sanitized errors and no implicit live calls."""

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from facet import __version__
from facet.config import ConfigError, dump_config, initial_template, load_config
from facet.contracts import (
    ErrorCode,
    LocalId,
    PolicyVersion,
    ProjectionId,
    Revision,
    Role,
    RuleKind,
    RuleOrigin,
    Timestamp,
)
from facet.private_paths import (
    inspect_state_root,
    read_managed_config,
    select_paths,
)

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
    run.add_argument("--fake", action="store_true", help="use offline synthetic Gmail")
    auth = commands.add_parser(
        "auth",
        add_help=False,
        allow_abbrev=False,
        help="authorize both configured Gmail roles",
    )
    _common(auth)
    auth_action = auth.add_subparsers(dest="action", parser_class=_Parser)
    authorize = auth_action.add_parser(
        "authorize",
        add_help=False,
        allow_abbrev=False,
        help="authorize and verify both roles",
    )
    _common(authorize)
    _mutations(authorize)
    authorize.add_argument(
        "--fake", action="store_true", help="use the offline synthetic provider"
    )
    rules = commands.add_parser(
        "rules", add_help=False, allow_abbrev=False, help="update admission rules"
    )
    _common(rules)
    rule_action = rules.add_subparsers(dest="action", parser_class=_Parser)
    add_rule = rule_action.add_parser(
        "add-sender",
        add_help=False,
        allow_abbrev=False,
        help="add one exact sender allow rule",
    )
    _common(add_rule)
    _mutations(add_rule)
    add_rule.add_argument("--sender", required=True)
    backfill = commands.add_parser(
        "backfill",
        add_help=False,
        allow_abbrev=False,
        help="preview or start discovery",
    )
    _common(backfill)
    backfill_action = backfill.add_subparsers(dest="action", parser_class=_Parser)
    preview = backfill_action.add_parser(
        "preview",
        add_help=False,
        allow_abbrev=False,
        help="create a write-free preview",
    )
    _common(preview)
    preview.add_argument("--fake", action="store_true")
    start = backfill_action.add_parser(
        "start", add_help=False, allow_abbrev=False, help="explicitly start a preview"
    )
    _common(start)
    _mutations(start)
    start.add_argument("--preview-id", required=True)
    start.add_argument("--fake", action="store_true")
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
            if read_managed_config(select_paths(str(parent), None)) == raw:
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
    raw = read_managed_config(paths)
    config = load_config(raw)
    if (
        getattr(options, "projection", None) is not None
        and ProjectionId(options.projection) != config.projection.id
    ):
        raise ConfigError(ErrorCode.BINDING_MISMATCH)
    owner = StateOwner.open(paths.root, config)
    try:
        locked_raw = read_managed_config(paths)
        if locked_raw != raw:
            raise ConfigError(ErrorCode.REQUEST_CONFLICT)
        owner.verify_config_artifact(locked_raw)
        bindings = owner.bindings()
        if any(
            binding is None or binding.state.value != "verified"
            for binding in bindings.values()
        ):
            raise ConfigError(ErrorCode.BINDING_PENDING)
        raise ConfigError(ErrorCode.SOURCE_AUTH_REQUIRED)
    finally:
        owner.close()


def _run_once_fake(options: object) -> tuple[dict, tuple[str, ...]]:
    from facet.contracts import PolicyVersion, ProviderId
    from facet.db.codecs import PrivateAddress
    from facet.gmail.source_auth import SyntheticSourceAuthProvider
    from facet.gmail.synthetic import SyntheticGmailServiceFactory
    from facet.projection.authenticity import (
        FromAlignment,
        SourcePathStatus,
        _issuer_for_tests,
    )
    from facet.runtime.foreground_runtime import run_foreground_once
    from facet.runtime.state_owner import StateOwner

    paths = select_paths(
        getattr(options, "state_dir", None), getattr(options, "config_path", None)
    )
    if getattr(options, "config_path", None) is not None:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    try:
        owner.verify_config_artifact(raw)
        evidence = _issuer_for_tests().issue(
            source_role=Role.SOURCE,
            source_account=PrivateAddress(config.projection.source_email),
            source_message_id=ProviderId("source-message"),
            source_path=SourcePathStatus.TRUSTED,
            from_alignment=FromAlignment.ALIGNED,
            binding_revision=owner.bindings()[Role.SOURCE].binding_revision,
            credential_revision=owner.bindings()[Role.SOURCE].credential_revision,
            observed_at=Timestamp(datetime.now(UTC) - timedelta(minutes=1)),
            expires_at=Timestamp(datetime.now(UTC) + timedelta(hours=1)),
            policy_version=PolicyVersion("auth-v1"),
        )
        receipt = run_foreground_once(
            owner,
            config,
            SyntheticGmailServiceFactory(
                config.projection.source_email, config.projection.target_email
            ),
            source_auth_provider=SyntheticSourceAuthProvider(evidence),
        )
        return {
            "discovered": receipt.discovered,
            "history_pages": receipt.history_pages,
            "resolved_events": receipt.resolved_events,
            "projected": receipt.projected.verified,
            "attention": receipt.attention,
        }, ()
    finally:
        owner.close()


def _auth_authorize(options: object) -> tuple[dict, tuple[str, ...]]:
    if not getattr(options, "fake", False):
        raise ConfigError(ErrorCode.SOURCE_AUTH_REQUIRED)
    if (
        not getattr(options, "yes", False)
        or getattr(options, "request_id", None) is None
    ):
        raise ConfigError(ErrorCode.CONFIRMATION_REQUIRED)
    try:
        request_nonce = LocalId(options.request_id)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    from facet.db import command_store
    from facet.gmail.credential_models import (
        AccountAddress,
        ClientIdText,
        ProviderSecret,
        SecretText,
        policy_scopes,
    )
    from facet.gmail.credentials import CredentialManager, ProfileEvidence
    from facet.private_paths import read_managed_config
    from facet.runtime.foreground_runtime import _policy
    from facet.runtime.state_owner import StateOwner

    paths = select_paths(getattr(options, "state_dir", None), None)
    config_raw = read_managed_config(paths)
    config = load_config(config_raw)
    owner = StateOwner.open(paths.root, config)
    try:
        owner.verify_config_artifact(config_raw)
        operation_ids = {}
        with owner.session.transaction() as uow:
            for role in Role:
                digest = bytearray(
                    hashlib.sha256(
                        (request_nonce.value + "\x00" + role.value).encode()
                    ).digest()[:16]
                )
                digest[6] = (digest[6] & 0x0F) | 0x40
                digest[8] = (digest[8] & 0x3F) | 0x80
                role_nonce = LocalId(UUID(bytes=bytes(digest)).hex)
                operation_ids[role] = command_store.authorize_operation(
                    uow, config.projection.id, role, role_nonce
                )

        class SyntheticProfiles:
            def get_profile(self, role, _secret):
                account = (
                    config.projection.source_email
                    if role is Role.SOURCE
                    else config.projection.target_email
                )
                return ProfileEvidence(
                    AccountAddress(account), policy_scopes(_policy(config, role), role)
                )

        expires = Timestamp(datetime.now(UTC) + timedelta(days=365))
        secrets = {
            role: ProviderSecret(
                ClientIdText("facet-synthetic-client"),
                SecretText("facet-synthetic-client-secret"),
                SecretText(f"facet-synthetic-{role.value}-access"),
                SecretText(f"facet-synthetic-{role.value}-refresh"),
                expires,
            )
            for role in Role
        }
        CredentialManager(owner.state_dir, config, owner).authorize(
            secrets, SyntheticProfiles(), operation_ids
        )
        return {"binding_state": "verified"}, ()
    finally:
        owner.close()


def _rules_add_sender(options: object) -> tuple[dict, tuple[str, ...]]:
    if (
        not getattr(options, "yes", False)
        or getattr(options, "request_id", None) is None
    ):
        raise ConfigError(ErrorCode.CONFIRMATION_REQUIRED)
    from facet.db.models import (
        RevisionGuard,
        RuleRevisionRow,
        RuleRow,
        RulesetMemberRow,
        RulesetRow,
    )
    from facet.db.repositories import policy
    from facet.db.repositories.base import _get
    from facet.projection.rules import normalize_rule
    from facet.runtime.state_owner import StateOwner

    try:
        LocalId(options.request_id)
        normalized = normalize_rule(RuleKind.ALLOW_SENDER, options.sender)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    paths = select_paths(getattr(options, "state_dir", None), None)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    try:
        owner.verify_config_artifact(raw)
        now = Timestamp(datetime.now(UTC))
        rule_id = LocalId(uuid4().hex)
        with owner.session.transaction() as uow:
            projection = _get(uow, config.projection.id, "projections", ())
            if projection is None:
                raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
            if projection.binding_state.value != "verified":
                raise ConfigError(ErrorCode.BINDING_PENDING)
            rule = RuleRow(
                config.projection.id,
                rule_id,
                normalized.kind,
                normalized.storage_value,
                Revision(1),
            )
            revision = RuleRevisionRow(
                config.projection.id,
                rule_id,
                Revision(1),
                True,
                now,
                RuleOrigin.CLI,
                PolicyVersion("auth-v1"),
            )
            snapshot = RulesetRow(
                config.projection.id,
                Revision(projection.ruleset_revision.value + 1),
                now,
                True,
            )
            policy.publish_rules(
                uow,
                config.projection.id,
                (rule,),
                (revision,),
                snapshot,
                (
                    RulesetMemberRow(
                        config.projection.id, snapshot.revision, rule_id, Revision(1)
                    ),
                ),
                RevisionGuard(projection.ruleset_revision),
            )
        return {"ruleset_revision": snapshot.revision.value}, ()
    finally:
        owner.close()


def _backfill_preview(options: object) -> tuple[dict, tuple[str, ...]]:
    from facet.contracts import Sha256Hex
    from facet.db.command_records import BackfillPreviewRequest
    from facet.db.command_store import preview_backfill
    from facet.runtime.state_owner import StateOwner

    paths = select_paths(getattr(options, "state_dir", None), None)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    try:
        now = Timestamp(datetime.now(UTC))
        month = now.value.year * 12 + now.value.month - 7
        year, month_index = divmod(month, 12)
        window_start = Timestamp(
            now.value.replace(
                year=year,
                month=month_index + 1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        )
        request = BackfillPreviewRequest(
            LocalId(uuid4().hex),
            LocalId(uuid4().hex),
            window_start,
            now,
            Timestamp(now.value.replace(day=1)),
            Sha256Hex(hashlib.sha256(b"facet-synthetic-scope-v1").hexdigest()),
            Timestamp(now.value + timedelta(minutes=10)),
            Revision(0),
            now,
        )
        with owner.session.transaction() as uow:
            operation = preview_backfill(uow, config.projection.id, request)
        return {"preview_id": operation.operation_id.value}, ()
    finally:
        owner.close()


def _backfill_start(options: object) -> tuple[dict, tuple[str, ...]]:
    from facet.contracts import ProviderId
    from facet.db.codecs import PrivateAddress
    from facet.db.command_records import BackfillStartRequest
    from facet.db.command_store import _find_backfill_by_id
    from facet.gmail.credentials import CredentialManager
    from facet.gmail.source import SourceAdapter
    from facet.gmail.synthetic import SyntheticGmailServiceFactory
    from facet.projection.backfill import BackfillProducer
    from facet.runtime.state_owner import StateOwner

    if not getattr(options, "fake", False):
        raise ConfigError(ErrorCode.SOURCE_AUTH_REQUIRED)
    try:
        preview_id = LocalId(options.preview_id)
        LocalId(options.request_id)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    paths = select_paths(getattr(options, "state_dir", None), None)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    try:
        manager = CredentialManager(owner.state_dir, config, owner)
        snapshot = manager.snapshot(Role.SOURCE)
        binding = owner.bindings()[Role.SOURCE]
        source = SourceAdapter(
            SyntheticGmailServiceFactory(
                config.projection.source_email, config.projection.target_email
            ).service(Role.SOURCE, snapshot),
            source_account=PrivateAddress(config.projection.source_email),
            binding_revision=binding.binding_revision,
            credential_revision=binding.credential_revision,
        )
        with owner.session.transaction() as uow:
            existing = _find_backfill_by_id(uow, config.projection.id, preview_id)
        if existing[0] is None:
            raise ConfigError(ErrorCode.PREVIEW_INVALID)
        preview, payload = existing
        start = BackfillStartRequest(
            LocalId(uuid4().hex),
            LocalId(options.request_id),
            preview.operation_id,
            LocalId(uuid4().hex),
            ProviderId("pending-history"),
            Timestamp(datetime.now(UTC)),
            Timestamp(datetime.now(UTC)),
        )

        class Admission:
            def evaluate(self, _item, _epoch):
                raise ConfigError(ErrorCode.SOURCE_AUTH_REQUIRED)

        _, epoch = BackfillProducer(source, Admission()).start(
            owner.session, config.projection.id, start
        )
        with owner.session.transaction() as uow:
            uow._execute(
                "UPDATE projections SET daemon_paused=0 WHERE projection_id=?",
                (config.projection.id.value,),
            )
        return {"epoch_id": epoch.epoch_id.value}, ()
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
            data, warnings = (
                _run_once_fake(options)
                if getattr(options, "fake", False)
                else _run_preflight(options)
            )
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family == "auth":
            if options.action != "authorize":
                raise _InputError()
            command = "auth.authorize"
            data, warnings = _auth_authorize(options)
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family == "rules":
            if options.action != "add-sender":
                raise _InputError()
            command = "rules.add-sender"
            data, warnings = _rules_add_sender(options)
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family == "backfill":
            if options.action == "preview":
                command = "backfill.preview"
                data, warnings = _backfill_preview(options)
            elif options.action == "start":
                command = "backfill.start"
                data, warnings = _backfill_start(options)
            else:
                raise _InputError()
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
