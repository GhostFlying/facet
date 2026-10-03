"""Private bounded installed no-state launch; no CLI route or provider input."""

import base64
import hashlib
import os
import selectors
import stat
import subprocess
import sys
import time

from facet.contracts import ErrorCode

_ENV = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
_SECONDS = 10
_BYTES = 256
_RESULTS = {
    b"facet: owner_unavailable\n": (4, ErrorCode.OWNER_UNAVAILABLE),
    b"facet: unsupported_version\n": (4, ErrorCode.UNSUPPORTED_VERSION),
    b"facet: persistence_failure\n": (7, ErrorCode.PERSISTENCE_FAILURE),
    b"facet: consistency_failure\n": (7, ErrorCode.CONSISTENCY_FAILURE),
    b"facet: invalid_input\n": (7, ErrorCode.INVALID_INPUT),
}


def _safe_entry(path, *, directory=False):
    info = os.lstat(path)
    if (
        info.st_uid not in (0, os.geteuid())
        or stat.S_IMODE(info.st_mode) & 0o022
        or (directory and not stat.S_ISDIR(info.st_mode))
        or (not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
    ):
        raise ValueError("owner_unavailable")
    return info.st_dev, info.st_ino, info.st_uid, info.st_mode


def _installed_entry():
    current = os.path.abspath(__file__)
    runtime = os.path.dirname(current)
    package = os.path.dirname(runtime)
    site = os.path.dirname(package)
    expected = os.path.join(
        sys.prefix,
        "lib",
        f"python{sys.version_info.major}.{sys.version_info.minor}",
        "site-packages",
    )
    if (
        site != expected
        or os.path.basename(package) != "facet"
        or os.path.basename(runtime) != "runtime"
        or current != os.path.join(runtime, "read_launcher.py")
    ):
        raise ValueError("owner_unavailable")
    for path in (sys.prefix, os.path.dirname(site), site, package, runtime):
        _safe_entry(path, directory=True)
    _safe_entry(current)
    bootstrap = os.path.join(runtime, "read_bootstrap.py")
    identity = _safe_entry(bootstrap)
    interpreter = os.path.abspath(sys.executable)
    executable = os.stat(interpreter)
    if (
        not stat.S_ISREG(executable.st_mode)
        or not executable.st_mode & 0o111
        or executable.st_uid not in (0, os.geteuid())
        or stat.S_IMODE(executable.st_mode) & 0o022
    ):
        raise ValueError("owner_unavailable")
    # Fixed metadata, not caller/config paths. An editable module is outside site.
    metadata = os.path.join(site, "facet_gmail_spike-0.1.0.dist-info", "METADATA")
    _safe_entry(metadata)
    with open(metadata, "rb") as stream:
        content = stream.read(65537)
    if (
        len(content) > 65536
        or b"\nName: facet-gmail-spike\n" not in content
        or b"\nVersion: 0.1.0\n" not in content
    ):
        raise ValueError("owner_unavailable")
    record = os.path.join(site, "facet_gmail_spike-0.1.0.dist-info", "RECORD")
    _safe_entry(record)
    with open(record, "rb") as stream:
        records = stream.read(65537)
    if len(records) > 65536:
        raise ValueError("owner_unavailable")
    for name in ("read_bootstrap.py", "read_launcher.py", "read_qualification.py"):
        target = os.path.join(runtime, name)
        _safe_entry(target)
        with open(target, "rb") as stream:
            code = stream.read(65537)
        if len(code) > 65536:
            raise ValueError("owner_unavailable")
        digest = base64.urlsafe_b64encode(hashlib.sha256(code).digest()).rstrip(b"=")
        prefix = ("facet/runtime/" + name + ",").encode("ascii")
        entries = [line for line in records.splitlines() if line.startswith(prefix)]
        expected = prefix + b"sha256=" + digest + b"," + str(len(code)).encode("ascii")
        if entries != [expected]:
            raise ValueError("owner_unavailable")
    return interpreter, bootstrap, identity


def _collect(process, deadline):
    output = {"stdout": bytearray(), "stderr": bytearray()}
    with selectors.DefaultSelector() as ready:
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            ready.register(stream, selectors.EVENT_READ, name)
        while ready.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("owner_unavailable")
            events = ready.select(remaining)
            if not events:
                raise TimeoutError("owner_unavailable")
            for key, _ in events:
                total = sum(map(len, output.values()))
                data = os.read(key.fileobj.fileno(), _BYTES + 1 - total)
                if not data:
                    ready.unregister(key.fileobj)
                else:
                    output[key.data].extend(data)
                    if sum(map(len, output.values())) > _BYTES:
                        raise ValueError("consistency_failure")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("owner_unavailable")
        process.wait(timeout=remaining)
    return bytes(output["stdout"]), bytes(output["stderr"])


def _launch_no_state_read_bootstrap():
    # Only this newly created child can be killed/reaped. No PID file is read.
    end = time.monotonic() + _SECONDS
    process = None
    result = ErrorCode.OWNER_UNAVAILABLE
    try:
        interpreter, bootstrap, identity = _installed_entry()
        process = subprocess.Popen(
            [interpreter, "-I", "-S", "-B", "-X", "utf8", bootstrap],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            env=_ENV.copy(),
        )
        # Reserve bounded cleanup inside the ten-second whole-call budget.
        stdout, stderr = _collect(process, end - 1.5)
        accepted = _RESULTS.get(stderr)
        if stdout or accepted is None or process.returncode != accepted[0]:
            result = ErrorCode.CONSISTENCY_FAILURE
        elif (interpreter, bootstrap, identity) != _installed_entry():
            result = ErrorCode.OWNER_UNAVAILABLE
        else:
            result = accepted[1]
    except (TimeoutError, FileNotFoundError, PermissionError):
        result = ErrorCode.OWNER_UNAVAILABLE
    except ValueError as error:
        result = (
            ErrorCode.OWNER_UNAVAILABLE
            if error.args == ("owner_unavailable",)
            else ErrorCode.CONSISTENCY_FAILURE
        )
    except BaseException:
        result = ErrorCode.CONSISTENCY_FAILURE
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
            except BaseException:
                result = ErrorCode.OWNER_UNAVAILABLE
            try:
                process.wait(timeout=max(0.01, end - time.monotonic()))
            except BaseException:
                result = ErrorCode.OWNER_UNAVAILABLE
            finally:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except BaseException:
                            result = ErrorCode.OWNER_UNAVAILABLE
    return result
