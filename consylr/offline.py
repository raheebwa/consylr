# SPDX-License-Identifier: MIT
"""The offline guarantee, made checkable rather than stated, per #28.

`SECURITY.md` treats a network call reachable at inference time as a
vulnerability rather than a performance note. A README sentence cannot be
falsified, so the property lives here as something a test can plant a violation
against — and something the CLI can report, so an operator who has never read
the test can still see what is being claimed.

**Egress is refused at `connect` and at name resolution, not at construction.**
Creating a socket object reaches nothing; libraries do it speculatively and
never dial. Resolving a name, by contrast, already leaves the machine and
already leaks what is being run, so a guard that stopped only `connect` would
let the lookup through and call the result offline.

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
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class NetworkAttempted(RuntimeError):
    """Something tried to reach the network while the guard was up.

    Raised rather than logged. A warning would leave the run to finish and the
    claim to be made anyway, which is the failure this whole module exists to
    prevent.
    """


@contextmanager
def no_network() -> Iterator[None]:
    """Refuse every outbound call for the duration of the block."""
    saved_connect = socket.socket.connect
    saved_connect_ex = socket.socket.connect_ex
    saved_create = socket.create_connection
    saved_getaddrinfo = socket.getaddrinfo
    saved_gethostbyname = socket.gethostbyname

    def refuse(what: str) -> Any:
        def refused(*args: Any, **kwargs: Any) -> Any:
            # The target is named. A bare "network disabled" leaves whoever
            # trips it guessing which dependency dialled out.
            target = args[1] if what == "connect" and len(args) > 1 else (args[0] if args else "")
            raise NetworkAttempted(
                f"inference attempted {what}({target!r}); this build is offline by construction"
            )

        return refused

    socket.socket.connect = refuse("connect")  # type: ignore[method-assign]
    socket.socket.connect_ex = refuse("connect_ex")  # type: ignore[method-assign]
    socket.create_connection = refuse("create_connection")
    socket.getaddrinfo = refuse("getaddrinfo")
    socket.gethostbyname = refuse("gethostbyname")
    try:
        yield
    finally:
        # Restored in `finally` so a failing body cannot leave the process with
        # a permanently broken socket module — every later test in the session
        # would then pass for the wrong reason.
        socket.socket.connect = saved_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = saved_connect_ex  # type: ignore[method-assign]
        socket.create_connection = saved_create
        socket.getaddrinfo = saved_getaddrinfo
        socket.gethostbyname = saved_gethostbyname
