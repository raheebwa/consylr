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
        assert socket.socket is not None


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


def test_a_raw_socket_connect_is_refused() -> None:
    with no_network(), pytest.raises(NetworkAttempted):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("127.0.0.1", 9))
        finally:
            s.close()


def test_the_guard_puts_everything_back() -> None:
    """A guard that leaks past its own block would make every later test in the
    session pass for the wrong reason."""
    before = (socket.socket.connect, socket.getaddrinfo, socket.create_connection)
    with no_network():
        pass
    assert (socket.socket.connect, socket.getaddrinfo, socket.create_connection) == before


def test_it_puts_everything_back_even_when_the_body_raises() -> None:
    before = socket.getaddrinfo
    with pytest.raises(ValueError), no_network():
        raise ValueError("something else went wrong")
    assert socket.getaddrinfo is before
