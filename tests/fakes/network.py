"""Explicit process-local Python network guard, not an OS network sandbox.

Subprocesses must install this guard themselves or use their owner's isolation.
Local AF_UNIX traffic is allowed only when explicitly requested by a test.
"""

import socket
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import patch


class NetworkDenied(RuntimeError):
    def __init__(self) -> None:
        super().__init__("external network denied by test guard")


@contextmanager
def deny_network(*, allow_unix: bool = False) -> Iterator[None]:
    def denied(*args: object, **kwargs: object) -> None:
        raise NetworkDenied()

    def guarded(original):
        def call(sock, *args, **kwargs):
            if allow_unix and sock.family == socket.AF_UNIX:
                return original(sock, *args, **kwargs)
            raise NetworkDenied()

        return call

    with ExitStack() as stack:
        for name in (
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
            "gethostbyaddr",
            "create_connection",
        ):
            stack.enter_context(patch.object(socket, name, denied))
        for name in ("connect", "connect_ex", "send", "sendall", "sendto", "sendmsg"):
            if hasattr(socket.socket, name):
                stack.enter_context(
                    patch.object(
                        socket.socket, name, guarded(getattr(socket.socket, name))
                    )
                )
        yield
