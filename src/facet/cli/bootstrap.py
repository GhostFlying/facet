"""Production CLI foundation, with sanitized errors and no implicit live calls."""

import argparse
import hashlib
import json
import math
import os
import signal
import stat
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

from facet import __version__
from facet.config import ConfigError, dump_config, initial_template, load_config
from facet.contracts import (
    BindingState,
    EpochState,
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


def _auth_role_nonce(request_nonce: LocalId, role: Role) -> LocalId:
    digest = bytearray(
        hashlib.sha256((request_nonce.value + "\x00" + role.value).encode()).digest()[
            :16
        ]
    )
    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80
    return LocalId(UUID(bytes=bytes(digest)).hex)


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
        description=("Facet private initialization and controlled Gmail projection."),
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
        help="run the foreground sync owner",
    )
    _common(run)
    run.add_argument("--once", action="store_true")
    run.add_argument("--fake", action="store_true", help="use offline synthetic Gmail")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8080)
    run.add_argument("--interval", type=float, default=5.0)
    status = commands.add_parser(
        "status",
        add_help=False,
        allow_abbrev=False,
        help="show aggregate local sync status",
    )
    _common(status)
    doctor = commands.add_parser(
        "doctor",
        add_help=False,
        allow_abbrev=False,
        help="check aggregate local sync health",
    )
    _common(doctor)
    doctor.add_argument(
        "--live",
        action="store_true",
        help="reserved for a separately-authorized remote check",
    )
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
    authorize.add_argument("--role", choices=("source", "target"))
    authorize.add_argument("--oauth-client")
    authorize.add_argument("--port", type=int, default=8080)
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
    add_domain = rule_action.add_parser(
        "add-domain",
        add_help=False,
        allow_abbrev=False,
        help="add one exact domain allow rule",
    )
    _common(add_domain)
    _mutations(add_domain)
    add_domain.add_argument("--domain", required=True)
    list_rules = rule_action.add_parser(
        "list",
        add_help=False,
        allow_abbrev=False,
        help="show aggregate persisted rule state",
    )
    _common(list_rules)
    show_rule = rule_action.add_parser(
        "show",
        add_help=False,
        allow_abbrev=False,
        help="show one persisted rule's private metadata",
    )
    _common(show_rule)
    show_rule.add_argument("--rule-id", required=True)
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
    preview.add_argument("--request-id", required=True)
    preview.add_argument("--fake", action="store_true")
    start = backfill_action.add_parser(
        "start", add_help=False, allow_abbrev=False, help="explicitly start a preview"
    )
    _common(start)
    _mutations(start)
    start.add_argument("--preview-id", required=True)
    start.add_argument("--fake", action="store_true")
    backfill_status = backfill_action.add_parser(
        "status",
        add_help=False,
        allow_abbrev=False,
        help="show aggregate backfill progress",
    )
    _common(backfill_status)
    queue = commands.add_parser(
        "queue",
        add_help=False,
        allow_abbrev=False,
        help="show aggregate projection queue state",
    )
    _common(queue)
    queue_action = queue.add_subparsers(dest="action", parser_class=_Parser)
    queue_list = queue_action.add_parser(
        "list",
        add_help=False,
        allow_abbrev=False,
        help="show aggregate queue counts",
    )
    _common(queue_list)
    queue_show = queue_action.add_parser(
        "show",
        add_help=False,
        allow_abbrev=False,
        help="show one queued job's private metadata",
    )
    _common(queue_show)
    queue_show.add_argument("--job-id", required=True)
    review = commands.add_parser(
        "review",
        add_help=False,
        allow_abbrev=False,
        help="show aggregate attention state",
    )
    _common(review)
    review_action = review.add_subparsers(dest="action", parser_class=_Parser)
    review_list = review_action.add_parser(
        "list",
        add_help=False,
        allow_abbrev=False,
        help="show categorized attention groups",
    )
    _common(review_list)
    web = commands.add_parser(
        "web",
        add_help=False,
        allow_abbrev=False,
        help="serve the read-only aggregate dashboard",
    )
    _common(web)
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8080)
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
    """Run one production foreground cycle after local readiness checks."""

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
        return _run_once_production(owner, config)
    finally:
        owner.close()


def _run_once_production(owner, config) -> tuple[dict, tuple[str, ...]]:
    """Dispatch one real-provider cycle through the reviewed runtime seam."""

    from facet.gmail.service_factory import GoogleGmailServiceFactory
    from facet.gmail.source_auth import DkimSourceAuthProvider
    from facet.runtime.foreground_runtime import run_foreground_once

    receipt = run_foreground_once(
        owner,
        config,
        GoogleGmailServiceFactory(),
        source_auth_provider=DkimSourceAuthProvider(),
    )
    return {
        "discovered": receipt.discovered,
        "history_pages": receipt.history_pages,
        "resolved_events": receipt.resolved_events,
        "projected": receipt.projected.verified,
        "attention": receipt.attention,
    }, ()


def _foreground_gate(owner) -> tuple[bool, ErrorCode | None]:
    """Check durable readiness without constructing or calling a Gmail client."""

    bindings = owner.bindings()
    if any(
        binding is None or binding.state is not BindingState.VERIFIED
        for binding in bindings.values()
    ):
        return False, ErrorCode.BINDING_PENDING
    with owner.session.transaction() as uow:
        row = uow._execute(
            "SELECT state FROM epochs WHERE projection_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (owner.projection_id.value,),
        ).fetchone()
    if row is None:
        return False, None
    try:
        state = EpochState(row[0])
    except ValueError:
        raise ConfigError(ErrorCode.CONSISTENCY_FAILURE) from None
    if state not in {
        EpochState.PREPARED,
        EpochState.SCANNING,
        EpochState.CATCHING_UP,
        EpochState.DRAINING,
    }:
        return False, ErrorCode.MAINTENANCE_REQUIRED
    return True, None


def _run_foreground_service(options: object) -> tuple[dict, tuple[str, ...]]:
    """Own one sync loop and one read-only Dashboard in the current process."""

    from facet.gmail.service_factory import GoogleGmailServiceFactory
    from facet.gmail.source_auth import DkimSourceAuthProvider
    from facet.runtime.dashboard import LiveSnapshotProvider
    from facet.runtime.foreground_runtime import run_foreground_once
    from facet.runtime.state_owner import StateOwner
    from facet.web.server import DashboardServer

    if getattr(options, "fake", False):
        raise ConfigError(ErrorCode.INVALID_INPUT)
    try:
        interval = float(options.interval)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    if not math.isfinite(interval) or interval <= 0 or interval > 86400:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    if not 1 <= options.port <= 65535 or not isinstance(options.host, str):
        raise ConfigError(ErrorCode.INVALID_INPUT)
    paths = select_paths(
        getattr(options, "state_dir", None), getattr(options, "config_path", None)
    )
    if getattr(options, "config_path", None) is not None:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    provider = LiveSnapshotProvider()
    stop = Event()
    server = None
    server_thread = None
    started = False
    previous_sigterm = None
    try:
        owner.verify_config_artifact(raw)
        server = DashboardServer((options.host, options.port), provider)
        server_thread = Thread(target=server.serve_forever, daemon=True)
        previous_sigterm = signal.signal(signal.SIGTERM, lambda *_: stop.set())
        server_thread.start()
        started = True
        while not stop.is_set():
            try:
                ready, gate_error = _foreground_gate(owner)
            except Exception:
                provider.invalidate()
                stop.wait(interval)
                continue
            if not ready:
                try:
                    provider.publish_from_owner(
                        owner,
                        config,
                        error_code=gate_error,
                        cycle_verified=False,
                    )
                except Exception:
                    provider.invalidate()
                stop.wait(interval)
                continue
            error_code = None
            try:
                run_foreground_once(
                    owner,
                    config,
                    GoogleGmailServiceFactory(),
                    source_auth_provider=DkimSourceAuthProvider(),
                )
            except KeyboardInterrupt:
                break
            except Exception as error:
                error_code = getattr(error, "code", ErrorCode.PERSISTENCE_FAILURE)
                if type(error_code) is not ErrorCode:
                    error_code = ErrorCode.PERSISTENCE_FAILURE
            try:
                provider.publish_from_owner(
                    owner,
                    config,
                    error_code=error_code,
                    cycle_verified=error_code is None,
                )
            except Exception:
                provider.invalidate()
            stop.wait(interval)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        if started and server is not None and server_thread is not None:
            server.shutdown()
            server_thread.join(timeout=2)
        if server is not None:
            server.server_close()
        owner.close()
    return {"stopped": True}, ()


def _run_once_fake(options: object) -> tuple[dict, tuple[str, ...]]:
    from facet.contracts import PolicyVersion, ProviderId
    from facet.db.codecs import PrivateAddress
    from facet.gmail.credentials import CredentialManager
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
        manager = CredentialManager(owner.state_dir, config, owner)
        snapshots = {role: manager.snapshot(role) for role in Role}
        if any(
            not snapshot.access_token.value.startswith("facet-synthetic-")
            for snapshot in snapshots.values()
        ):
            raise ConfigError(ErrorCode.SOURCE_AUTH_REQUIRED)
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


def _auth_authorize_oauth(options: object) -> tuple[dict, tuple[str, ...]]:
    if (
        getattr(options, "role", None) not in {"source", "target"}
        or getattr(options, "oauth_client", None) is None
        or getattr(options, "fake", False)
        or not getattr(options, "yes", False)
        or getattr(options, "request_id", None) is None
        or not sys.stdin.isatty()
        or not sys.stdout.isatty()
        or not sys.stderr.isatty()
    ):
        raise ConfigError(ErrorCode.CONFIRMATION_REQUIRED)
    try:
        role = Role(options.role)
        request_nonce = LocalId(options.request_id)
        port = int(options.port)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    if not 1024 <= port <= 65535:
        raise ConfigError(ErrorCode.INVALID_INPUT)
    from facet.db import command_store
    from facet.gmail.credential_models import policy_scopes
    from facet.gmail.credentials import CredentialManager
    from facet.gmail.oauth import GoogleOAuthAuthorizer, read_desktop_client
    from facet.gmail.service_factory import GoogleGmailServiceFactory
    from facet.private_paths import read_managed_config
    from facet.runtime.foreground_runtime import _policy
    from facet.runtime.state_owner import StateOwner

    paths = select_paths(getattr(options, "state_dir", None), None)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    try:
        owner.verify_config_artifact(raw)
        with owner.session.transaction() as uow:
            rule_collision = uow._execute(
                "SELECT 1 FROM rules WHERE projection_id=? AND rule_id=? LIMIT 1",
                (config.projection.id.value, request_nonce.value),
            ).fetchone()
        if rule_collision:
            raise ConfigError(ErrorCode.REQUEST_CONFLICT)
        existing = False
        with owner.session.transaction() as uow:
            existing_rows = uow._execute(
                "SELECT command,state FROM operations WHERE projection_id=? "
                "AND request_namespace=? AND request_nonce=? LIMIT 2",
                (
                    config.projection.id.value,
                    owner.owner_info.request_namespace.value,
                    request_nonce.value,
                ),
            ).fetchall()
        if any(command != "auth_authorize" for command, _state in existing_rows):
            raise ConfigError(ErrorCode.REQUEST_CONFLICT)
        existing = bool(existing_rows)
        with owner.session.transaction() as uow:
            operation_id = command_store.authorize_operation(
                uow, config.projection.id, role, request_nonce
            )
            row = uow._execute(
                "SELECT state FROM operations WHERE projection_id=? "
                "AND operation_id=? LIMIT 2",
                (config.projection.id.value, operation_id.value),
            ).fetchall()
        if len(row) != 1:
            raise ConfigError(ErrorCode.CONSISTENCY_FAILURE)
        if row[0][0] == "completed":
            return {"role": role.value, "binding_state": "verified"}, ()
        if existing and owner.bindings()[role].state.value != "verified":
            with owner.session.transaction() as uow:
                changes = uow._execute(
                    "SELECT phase FROM credential_changes WHERE "
                    "projection_id=? AND operation_id=? AND role=? LIMIT 2",
                    (
                        config.projection.id.value,
                        operation_id.value,
                        role.value,
                    ),
                ).fetchall()
            if changes:
                raise ConfigError(ErrorCode.MAINTENANCE_REQUIRED)
            raise ConfigError(ErrorCode.REQUEST_OUTCOME_UNKNOWN)
        if owner.bindings()[role].state.value == "verified":
            from facet.db.repositories import credentials as credential_rows

            with owner.session.transaction() as uow:
                changes = uow._execute(
                    "SELECT change_id FROM credential_changes WHERE "
                    "projection_id=? AND operation_id=? AND role=? LIMIT 2",
                    (
                        config.projection.id.value,
                        operation_id.value,
                        role.value,
                    ),
                ).fetchall()
                change = (
                    credential_rows.get_change(
                        uow,
                        config.projection.id,
                        role,
                        LocalId(changes[0][0]),
                    )
                    if len(changes) == 1
                    else None
                )
            if change is None:
                raise ConfigError(ErrorCode.CONSISTENCY_FAILURE)
            if change.phase not in {"validated", "committed"}:
                raise ConfigError(ErrorCode.MAINTENANCE_REQUIRED)
            with owner.session.transaction() as uow:
                if change.phase == "validated":
                    credential_rows.commit_authorization(
                        uow, config.projection.id, change
                    )
                command_store.complete_authorize_operation(
                    uow, config.projection.id, operation_id
                )
            return {"role": role.value, "binding_state": "verified"}, ()
        client = read_desktop_client(options.oauth_client)
        oauth_result = GoogleOAuthAuthorizer().authorize(
            role,
            client,
            policy_scopes(_policy(config, role), role),
            port=port,
        )
        factory = GoogleGmailServiceFactory()

        class OAuthProfileProbe:
            def get_profile(self, probe_role, secret):
                account = factory.profile_account(probe_role, secret)
                from facet.gmail.credentials import ProfileEvidence

                return ProfileEvidence(account, oauth_result.scopes)

        CredentialManager(owner.state_dir, config, owner).authorize_role(
            role,
            oauth_result.secret,
            OAuthProfileProbe(),
            operation_id,
        )
        with owner.session.transaction() as uow:
            command_store.complete_authorize_operation(
                uow, config.projection.id, operation_id
            )
        return {"role": role.value, "binding_state": "verified"}, ()
    finally:
        owner.close()


def _auth_authorize(options: object) -> tuple[dict, tuple[str, ...]]:
    if not getattr(options, "fake", False):
        return _auth_authorize_oauth(options)
    if (
        getattr(options, "oauth_client", None) is not None
        or getattr(options, "role", None) is not None
    ):
        raise ConfigError(ErrorCode.INVALID_INPUT)
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
        # A rule command owns the raw request nonce.  Check this before
        # registering the two role-specific authorization operations so a
        # cross-command reuse is reported as a request conflict, not as a
        # transaction consistency failure.
        with owner.session.transaction() as uow:
            rule_collision = uow._execute(
                "SELECT 1 FROM rules WHERE projection_id=? AND rule_id=? LIMIT 1",
                (config.projection.id.value, request_nonce.value),
            ).fetchone()
        if rule_collision:
            raise ConfigError(ErrorCode.REQUEST_CONFLICT)
        operation_ids = {}
        replayed = True
        with owner.session.transaction() as uow:
            for role in Role:
                role_nonce = _auth_role_nonce(request_nonce, role)
                operation_ids[role] = command_store.authorize_operation(
                    uow, config.projection.id, role, role_nonce
                )
                row = uow._execute(
                    "SELECT state FROM operations WHERE projection_id=? "
                    "AND operation_id=? LIMIT 2",
                    (config.projection.id.value, operation_ids[role].value),
                ).fetchall()
                if len(row) != 1:
                    raise ConfigError(ErrorCode.CONSISTENCY_FAILURE)
                replayed = replayed and row[0][0] == "completed"

        if replayed:
            return {"binding_state": "verified"}, ()

        # A process can stop after binding publication but before recording
        # both command receipts. Recover that exact request only when its two
        # credential changes are present; a fresh request cannot piggyback on
        # an unrelated already-verified binding.
        if all(
            binding is not None and binding.state.value == "verified"
            for binding in owner.bindings().values()
        ):
            from facet.db.repositories import credentials as credential_rows

            recoverable = True
            with owner.session.transaction() as uow:
                for role in Role:
                    row = uow._execute(
                        "SELECT change_id FROM credential_changes WHERE "
                        "projection_id=? AND operation_id=? AND role=? LIMIT 2",
                        (
                            config.projection.id.value,
                            operation_ids[role].value,
                            role.value,
                        ),
                    ).fetchall()
                    if len(row) != 1:
                        recoverable = False
                        break
                    change = credential_rows.get_change(
                        uow,
                        config.projection.id,
                        role,
                        LocalId(row[0][0]),
                    )
                    if change.phase == "validated":
                        credential_rows.commit_authorization(
                            uow, config.projection.id, change
                        )
                    elif change.phase != "committed":
                        recoverable = False
                        break
                if recoverable:
                    for operation_id in operation_ids.values():
                        command_store.complete_authorize_operation(
                            uow, config.projection.id, operation_id
                        )
            if recoverable:
                return {"binding_state": "verified"}, ()

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
        with owner.session.transaction() as uow:
            for operation_id in operation_ids.values():
                command_store.complete_authorize_operation(
                    uow, config.projection.id, operation_id
                )
        return {"binding_state": "verified"}, ()
    finally:
        owner.close()


def _rules_add(
    options: object, kind: RuleKind, value: str
) -> tuple[dict, tuple[str, ...]]:
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
    from facet.db.repositories.base import _decode, _get
    from facet.projection.rules import normalize_rule
    from facet.runtime.state_owner import StateOwner

    try:
        request_id = LocalId(options.request_id)
        normalized = normalize_rule(kind, value)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    paths = select_paths(getattr(options, "state_dir", None), None)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    try:
        owner.verify_config_artifact(raw)
        now = Timestamp(datetime.now(UTC))
        rule_id = request_id
        auth_nonces = tuple(_auth_role_nonce(request_id, role).value for role in Role)
        with owner.session.transaction() as uow:
            occupied = uow._execute(
                "SELECT 1 FROM operations WHERE projection_id=? AND "
                "request_nonce IN (?,?,?) LIMIT 1",
                (config.projection.id.value, request_id.value, *auth_nonces),
            ).fetchone()
            projection = _get(uow, config.projection.id, "projections", ())
            existing_rule = _get(
                uow, config.projection.id, "rules", (("rule_id", rule_id),)
            )
            members = (
                uow._execute(
                    "SELECT ruleset_revision FROM ruleset_members WHERE "
                    "projection_id=? AND rule_id=? "
                    "ORDER BY ruleset_revision ASC LIMIT 1",
                    (config.projection.id.value, rule_id.value),
                ).fetchall()
                if existing_rule is not None
                else ()
            )
        if occupied:
            raise ConfigError(ErrorCode.REQUEST_CONFLICT)
        if existing_rule is not None:
            if (
                existing_rule.kind is not normalized.kind
                or existing_rule.normalized_value != normalized.storage_value
            ):
                raise ConfigError(ErrorCode.REQUEST_CONFLICT)
            if not members:
                raise ConfigError(ErrorCode.CONSISTENCY_FAILURE)
            return {"ruleset_revision": members[0][0]}, ()
        if projection is None:
            raise ConfigError(ErrorCode.OWNER_UNAVAILABLE)
        if projection.binding_state.value != "verified":
            raise ConfigError(ErrorCode.BINDING_PENDING)
        with owner.session.transaction() as uow:
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
            current_members = tuple(
                RulesetMemberRow(
                    config.projection.id,
                    snapshot.revision,
                    member.rule_id,
                    member.rule_revision,
                )
                for member in (
                    _decode(uow, config.projection.id, "ruleset_members", row)
                    for row in uow._execute(
                        "SELECT projection_id,ruleset_revision,rule_id,rule_revision "
                        "FROM ruleset_members WHERE projection_id=? AND "
                        "ruleset_revision=?",
                        (
                            config.projection.id.value,
                            projection.ruleset_revision.value,
                        ),
                    ).fetchall()
                )
            )
            policy.publish_rules(
                uow,
                config.projection.id,
                (rule,),
                (revision,),
                snapshot,
                current_members
                + (
                    RulesetMemberRow(
                        config.projection.id, snapshot.revision, rule_id, Revision(1)
                    ),
                ),
                RevisionGuard(projection.ruleset_revision),
            )
        return {"ruleset_revision": snapshot.revision.value}, ()
    finally:
        owner.close()


def _rules_add_sender(options: object) -> tuple[dict, tuple[str, ...]]:
    return _rules_add(options, RuleKind.ALLOW_SENDER, options.sender)


def _rules_add_domain(options: object) -> tuple[dict, tuple[str, ...]]:
    return _rules_add(options, RuleKind.ALLOW_DOMAIN, options.domain)


def _preview_summary(operation, payload) -> dict:
    def timestamp(value):
        return value.value.isoformat().replace("+00:00", "Z")

    return {
        "preview_id": operation.operation_id.value,
        "window_start": timestamp(payload.window_start),
        "window_end": timestamp(payload.window_end),
        "discovery_cutoff": timestamp(payload.discovery_cutoff),
        "ruleset_revision": payload.ruleset_revision.value,
        "target_writes": 0,
        "requires_explicit_start": True,
        "disclosure": {
            "scope": "source_thread",
            "includes_available_non_draft_history": True,
            "includes_attachments_participants_and_replies": True,
            "continues_for_future_thread_messages": True,
        },
    }


def _backfill_preview(options: object) -> tuple[dict, tuple[str, ...]]:
    from facet.contracts import Sha256Hex
    from facet.db.command_records import BackfillPreviewRequest
    from facet.db.command_store import (
        _find_backfill,
        _find_backfill_by_id,
        preview_backfill,
    )
    from facet.runtime.state_owner import StateOwner

    try:
        request_nonce = LocalId(options.request_id)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    paths = select_paths(getattr(options, "state_dir", None), None)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    try:
        auth_nonces = tuple(
            _auth_role_nonce(request_nonce, role).value for role in Role
        )
        with owner.session.transaction() as uow:
            occupied = uow._execute(
                "SELECT 1 FROM operations WHERE projection_id=? AND "
                "request_nonce IN (?,?) LIMIT 1",
                (config.projection.id.value, *auth_nonces),
            ).fetchone()
            rule_collision = uow._execute(
                "SELECT 1 FROM rules WHERE projection_id=? AND rule_id=? LIMIT 1",
                (config.projection.id.value, request_nonce.value),
            ).fetchone()
            existing = _find_backfill(
                uow,
                config.projection.id,
                owner.owner_info.request_namespace,
                request_nonce,
            )
        if occupied or rule_collision:
            raise ConfigError(ErrorCode.REQUEST_CONFLICT)
        if existing[0] is not None:
            if existing[0].command.value != "backfill_preview":
                raise ConfigError(ErrorCode.REQUEST_CONFLICT)
            return _preview_summary(existing[0], existing[1]), ()
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
            request_nonce,
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
        with owner.session.transaction() as uow:
            saved_operation, payload = _find_backfill_by_id(
                uow, config.projection.id, operation.operation_id, operation
            )
        if saved_operation is None or payload is None:
            raise ConfigError(ErrorCode.CONSISTENCY_FAILURE)
        return _preview_summary(saved_operation, payload), ()
    finally:
        owner.close()


def _backfill_start(options: object) -> tuple[dict, tuple[str, ...]]:
    from facet.contracts import ProviderId
    from facet.db.codecs import PrivateAddress
    from facet.db.command_records import BackfillStartRequest
    from facet.db.command_store import (
        _find_backfill,
        _find_backfill_by_id,
        resume_projection,
    )
    from facet.gmail.credentials import CredentialManager
    from facet.gmail.service_factory import GoogleGmailServiceFactory
    from facet.gmail.source import SourceAdapter
    from facet.gmail.synthetic import SyntheticGmailServiceFactory
    from facet.projection.backfill import BackfillProducer
    from facet.runtime.state_owner import StateOwner

    fake = getattr(options, "fake", False)
    try:
        preview_id = LocalId(options.preview_id)
        request_nonce = LocalId(options.request_id)
    except (TypeError, ValueError):
        raise ConfigError(ErrorCode.INVALID_INPUT) from None
    paths = select_paths(getattr(options, "state_dir", None), None)
    raw = read_managed_config(paths)
    config = load_config(raw)
    owner = StateOwner.open(paths.root, config)
    try:
        auth_nonces = tuple(
            _auth_role_nonce(request_nonce, role).value for role in Role
        )
        with owner.session.transaction() as uow:
            occupied = uow._execute(
                "SELECT 1 FROM operations WHERE projection_id=? AND "
                "request_nonce IN (?,?) LIMIT 1",
                (config.projection.id.value, *auth_nonces),
            ).fetchone()
            rule_collision = uow._execute(
                "SELECT 1 FROM rules WHERE projection_id=? AND rule_id=? LIMIT 1",
                (config.projection.id.value, request_nonce.value),
            ).fetchone()
            existing_start = _find_backfill(
                uow,
                config.projection.id,
                owner.owner_info.request_namespace,
                request_nonce,
            )
        if occupied or rule_collision:
            raise ConfigError(ErrorCode.REQUEST_CONFLICT)
        if existing_start[0] is not None:
            if (
                existing_start[0].command.value != "backfill_start"
                or existing_start[0].expected_preview_id != preview_id
            ):
                raise ConfigError(ErrorCode.REQUEST_CONFLICT)
            with owner.session.transaction() as uow:
                row = uow._execute(
                    "SELECT epoch_id FROM epochs WHERE projection_id=? "
                    "AND operation_id=? LIMIT 2",
                    (
                        config.projection.id.value,
                        existing_start[0].operation_id.value,
                    ),
                ).fetchall()
                epoch_id = row[0][0] if len(row) == 1 else None
                if epoch_id is not None:
                    resume_projection(uow, config.projection.id)
            if epoch_id is None:
                raise ConfigError(ErrorCode.MAINTENANCE_REQUIRED)
            return {"epoch_id": epoch_id}, ()
        with owner.session.transaction() as uow:
            existing = _find_backfill_by_id(uow, config.projection.id, preview_id)
        if existing[0] is None:
            raise ConfigError(ErrorCode.PREVIEW_INVALID)
        preview, payload = existing
        if any(
            binding is None or binding.state.value != "verified"
            for binding in owner.bindings().values()
        ):
            raise ConfigError(ErrorCode.BINDING_PENDING)
        manager = CredentialManager(owner.state_dir, config, owner)
        snapshot = manager.snapshot(Role.SOURCE)
        binding = owner.bindings()[Role.SOURCE]
        if fake:
            if not snapshot.access_token.value.startswith("facet-synthetic-"):
                raise ConfigError(ErrorCode.SOURCE_AUTH_REQUIRED)
            factory = SyntheticGmailServiceFactory(
                config.projection.source_email, config.projection.target_email
            )
        else:
            factory = GoogleGmailServiceFactory()
        source = SourceAdapter(
            factory.service(Role.SOURCE, snapshot),
            source_account=PrivateAddress(config.projection.source_email),
            binding_revision=binding.binding_revision,
            credential_revision=binding.credential_revision,
        )
        start = BackfillStartRequest(
            LocalId(uuid4().hex),
            request_nonce,
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
        ErrorCode.MAINTENANCE_REQUIRED: 4,
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
            if getattr(options, "once", False):
                data, warnings = (
                    _run_once_fake(options)
                    if getattr(options, "fake", False)
                    else _run_preflight(options)
                )
            else:
                data, warnings = _run_foreground_service(options)
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family in {"status", "doctor"}:
            command = options.family
            if getattr(options, "live", False):
                raise ConfigError(ErrorCode.INVALID_INPUT)
            from facet.cli.status import read_status

            result = read_status(options, doctor=options.family == "doctor")
            return _emit(
                command,
                code=result.code if options.family == "doctor" else None,
                data=result.data,
                json_mode=json_mode,
            )
        if options.family == "web":
            command = "web"
            if not 1 <= options.port <= 65535:
                raise _InputError()
            from facet.web.server import serve_dashboard

            serve_dashboard(options.host, options.port)
            return 0
        if options.family == "auth":
            if options.action != "authorize":
                raise _InputError()
            command = "auth.authorize"
            data, warnings = _auth_authorize(options)
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family == "rules":
            if options.action == "add-sender":
                command = "rules.add-sender"
                data, warnings = _rules_add_sender(options)
            elif options.action == "add-domain":
                command = "rules.add-domain"
                data, warnings = _rules_add_domain(options)
            elif options.action in {"list", "show"}:
                command = f"rules.{options.action}"
                from facet.cli.rule_views import read_rules

                data = read_rules(options, show=options.action == "show")
                warnings = ()
            else:
                raise _InputError()
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family == "backfill":
            if options.action == "preview":
                command = "backfill.preview"
                data, warnings = _backfill_preview(options)
            elif options.action == "start":
                command = "backfill.start"
                data, warnings = _backfill_start(options)
            elif options.action == "status":
                command = "backfill.status"
                from facet.cli.status import read_status

                result = read_status(options)
                data, warnings = result.data["progress"], ()
            else:
                raise _InputError()
            return _emit(command, data=data, warnings=warnings, json_mode=json_mode)
        if options.family == "queue":
            if options.action == "show":
                command = "queue.show"
                from facet.cli.queue_views import read_queue_job

                data = read_queue_job(options)
                return _emit(command, data=data, json_mode=json_mode)
            if options.action != "list":
                raise _InputError()
            command = "queue.list"
            from facet.cli.status import read_status

            result = read_status(options)
            progress = result.data["progress"]
            progress_data = progress["data"]
            data = {
                "jobs": progress_data["jobs"],
                "oldest_runnable_job_age_seconds": progress_data[
                    "oldest_runnable_job_age_seconds"
                ],
                "sampled_at": progress["sampled_at"],
                "freshness": progress["freshness"],
                "age_seconds": progress["age_seconds"],
                "scope": progress["scope"],
            }
            return _emit(command, data=data, json_mode=json_mode)
        if options.family == "review":
            if options.action != "list":
                raise _InputError()
            command = "review.list"
            from facet.cli.status import read_status

            result = read_status(options)
            return _emit(
                command,
                data=result.data["issues"],
                json_mode=json_mode,
            )
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
