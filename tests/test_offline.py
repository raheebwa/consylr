# SPDX-License-Identifier: MIT
"""Tests for the offline guarantee, per #28.

The offline property is the central claim of this project, so SECURITY.md treats
a network call reachable at inference as a vulnerability rather than a
performance note. That makes it a test, and a test of this kind is only worth
what its planted violations prove: a guard that has never been shown to catch
anything is a guard nobody has checked.

Every violation here is planted through a path this project did not write — a
dependency reaching the network is the case that matters, because our own code
not calling out is the easy half.
"""

import socket
import urllib.request

import pytest

from consylr.offline import NetworkAttempted, no_network


def test_local_work_is_untouched() -> None:
    """The guard must not be a general-purpose brake. Everything that is not
    egress carries on."""
    with no_network():
        assert sum(range(10)) == 45


def test_a_planted_outbound_connection_is_refused() -> None:
    with no_network(), pytest.raises(NetworkAttempted):
        socket.create_connection(("example.invalid", 80), timeout=0.1)


def test_a_planted_call_through_a_dependency_is_refused() -> None:
    """urllib is not our code. A guard that only catches calls we wrote would
    pass while a library phoned home underneath it."""
    with no_network(), pytest.raises(NetworkAttempted):
        urllib.request.urlopen("http://example.invalid/", timeout=0.1)


def test_a_name_lookup_is_itself_a_network_call() -> None:
    """DNS leaves the machine and leaks what is being run. Refusing only
    `connect` would let the lookup through and call the result offline."""
    with no_network(), pytest.raises(NetworkAttempted):
        socket.getaddrinfo("example.invalid", 80)


def test_an_internet_socket_cannot_be_created_at_all() -> None:
    """The boundary is creation, not use. Enumerating egress methods covers what
    the author thought of rather than what egress is — `sendto` on a datagram
    socket leaves the host with no connect and no lookup to intercept, and the
    next protocol nobody has considered will do the same. A socket that cannot
    exist cannot leak through an API neither of us has read."""
    for family in (socket.AF_INET, socket.AF_INET6):
        with no_network(), pytest.raises(NetworkAttempted):
            socket.socket(family, socket.SOCK_STREAM)


def test_connectionless_egress_is_refused() -> None:
    """One violation per API family, not per function name. A datagram to a
    literal address needs neither connect nor getaddrinfo; before the boundary
    moved to creation, this left the machine and the run still called itself
    offline."""
    with no_network(), pytest.raises(NetworkAttempted):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b"x", ("8.8.8.8", 53))


def test_a_local_socket_is_still_allowed() -> None:
    """The claim is no egress, not no sockets. Refusing AF_UNIX would break
    local machinery for a property it cannot affect."""
    with no_network():
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).close()


def test_the_other_resolvers_are_refused_too() -> None:
    """A second fence behind the boundary: some resolvers reach libc without
    ever constructing a Python socket object."""
    with no_network():
        for call in (
            lambda: socket.gethostbyname_ex("example.invalid"),
            lambda: socket.getfqdn("example.invalid"),
            lambda: socket.gethostbyaddr("127.0.0.1"),
        ):
            with pytest.raises(NetworkAttempted):
                call()


#: Every name the guard replaces. Spelled out so a symbol added to the guard and
#: forgotten in the restore is a failing test rather than a socket module left
#: broken for the rest of the interpreter.
PATCHED = (
    "getaddrinfo",
    "gethostbyname",
    "gethostbyname_ex",
    "gethostbyaddr",
    "getnameinfo",
    "getfqdn",
    "create_connection",
)


def test_the_guard_puts_everything_back() -> None:
    """A guard that leaks past its own block would make every later test in the
    session pass for the wrong reason. Checked over every patched symbol, not a
    sample of them: the ones a sample omits are exactly the ones that get
    forgotten."""
    before = {name: getattr(socket, name) for name in PATCHED}
    before_init = socket.socket.__init__
    with no_network():
        pass
    assert {name: getattr(socket, name) for name in PATCHED} == before
    assert socket.socket.__init__ is before_init


def test_it_puts_everything_back_even_when_the_body_raises() -> None:
    before = socket.getaddrinfo
    with pytest.raises(ValueError), no_network():
        raise ValueError("something else went wrong")
    assert socket.getaddrinfo is before
