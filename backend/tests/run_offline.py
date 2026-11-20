"""Run the unit test suite with all non-loopback network access blocked.

Usage (from backend/):  python tests/run_offline.py [unittest args...]

Any attempt to resolve or connect to a non-local host (cloud APIs, model hubs,
telemetry) raises inside the test and is reported here, and the run fails even
if the code under test swallowed the error. This enforces the project rule
that unit tests never touch the network.
"""

import os
import socket
import sys
import unittest

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "", None}
_attempts = []
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_getaddrinfo = socket.getaddrinfo


def _is_local(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    return host in _LOCAL_HOSTS or str(host).startswith("127.")


def _guard(address) -> None:
    if not _is_local(address):
        _attempts.append(address)
        raise OSError(f"network access blocked in unit tests: {address!r}")


def _connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _guard(address)
    return _original_connect(self, address)


def _connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _guard(address)
    return _original_connect_ex(self, address)


def _getaddrinfo(host, *args, **kwargs):
    _guard((host,))
    return _original_getaddrinfo(host, *args, **kwargs)


def main(argv=None) -> int:
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
    socket.getaddrinfo = _getaddrinfo
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(tests_dir)
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    program = unittest.main(
        module=None,
        argv=["run_offline", "discover", "-s", tests_dir, "-t", tests_dir, *(argv or [])],
        exit=False,
    )
    if _attempts:
        unique = sorted({repr(a) for a in _attempts})
        print(f"\nFAILED: tests attempted network access: {', '.join(unique)}", file=sys.stderr)
        return 1
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
