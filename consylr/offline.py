# SPDX-License-Identifier: MIT
"""The offline guarantee, made checkable rather than stated, per #28.

`SECURITY.md` treats a network call reachable at inference time as a
vulnerability rather than a performance note. A README sentence cannot be
falsified, so the property lives here as something a test can plant a violation
against — and something the CLI can report, so an operator who has never read
the test can still see what is being claimed.

**The boundary is socket creation, not socket use.** An earlier version refused
`connect`, `connect_ex`, `create_connection` and two resolvers — and a datagram
socket walked straight past all five: `sendto` to a literal address leaves the
host with no connect and no lookup to intercept. Enumerating egress methods
covers what the author thought of rather than what egress is, and the next
protocol nobody has read about will do the same thing again. **A socket that
cannot exist cannot leak.** So `AF_INET` and `AF_INET6` are refused at
construction, which collapses TCP, UDP, QUIC and everything after them into one
rule. `AF_UNIX` is allowed: the claim is no egress, not no sockets.

Name resolution keeps its own patches as a second fence, because some resolvers
reach libc without ever constructing a Python socket object — and a lookup
already leaves the machine and already leaks what is being run.

**Nothing here distinguishes our code from a dependency's**, because the case
that matters is the one we did not write. The patches sit on `socket` itself,
which is the floor every Python network client stands on — `urllib`, `requests`,
`httpx` and the HTTP layer inside a model loader all arrive here in the end.

The one permitted network operation is fetching weights at setup, and it is
outside this guard by construction: setup is a separate command that runs before
inference and never inside it.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class NetworkAttempted(RuntimeError):
    """Something tried to reach the network while the guard was up.

    Raised rather than logged. A warning would leave the run to finish and the
    claim to be made anyway, which is the failure this whole module exists to
    prevent.
    """


#: The patches are process-global, so only the outermost guard may install or
#: restore them. Two unsynchronised guards saved and restored the same symbols
#: independently: one interleaving left the refusals installed for the rest of
#: the interpreter, and the mirror one disarmed a guard while generation was
#: still running -- and the run reported itself offline anyway.
_DEPTH_LOCK = threading.RLock()
_depth = 0
_saved: dict[str, Any] = {}


@contextmanager
def no_network() -> Iterator[None]:
    """Refuse every outbound call for the duration of the block.

    Re-entrant and safe across threads: nesting or overlapping guards share one
    installation, and the module is restored only when the last one exits.
    """
    global _depth
    with _DEPTH_LOCK:
        _depth += 1
        outermost = _depth == 1
    try:
        if outermost:
            with _DEPTH_LOCK:
                _install()
        yield
    finally:
        with _DEPTH_LOCK:
            _depth -= 1
            if _depth == 0:
                _restore()


def _restore() -> None:
    socket.socket.__init__ = _saved.pop("__init__")  # type: ignore[method-assign]
    socket.create_connection = _saved.pop("create_connection")
    for name, original in _saved.items():
        setattr(socket, name, original)
    _saved.clear()


def _install() -> None:
    saved_init = socket.socket.__init__
    saved_create = socket.create_connection
    saved_resolvers = {
        name: getattr(socket, name)
        for name in (
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
            "gethostbyaddr",
            "getnameinfo",
            "getfqdn",
        )
    }
    #: Everything that is not a local socket. Named as an allow-list so a family
    #: nobody has heard of is refused by default rather than admitted by default.
    local = {getattr(socket, name) for name in ("AF_UNIX",) if hasattr(socket, name)}

    def refuse(what: str) -> Any:
        def refused(*args: Any, **kwargs: Any) -> Any:
            # The target is named. A bare "network disabled" leaves whoever
            # trips it guessing which dependency dialled out.
            target = args[1] if what == "connect" and len(args) > 1 else (args[0] if args else "")
            raise NetworkAttempted(
                f"inference attempted {what}({target!r}); this build is offline by construction"
            )

        return refused

    def refuse_socket(self: Any, family: Any = socket.AF_INET, *args: Any, **kwargs: Any) -> None:
        if family not in local:
            raise NetworkAttempted(
                f"inference attempted to create a {family!r} socket; this build is "
                "offline by construction"
            )
        saved_init(self, family, *args, **kwargs)

    socket.socket.__init__ = refuse_socket  # type: ignore[method-assign]
    socket.create_connection = refuse("create_connection")
    for name in saved_resolvers:
        setattr(socket, name, refuse(name))
    _saved["__init__"] = saved_init
    _saved["create_connection"] = saved_create
    _saved.update(saved_resolvers)
