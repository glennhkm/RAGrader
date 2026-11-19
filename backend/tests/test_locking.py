"""Concurrency tests for replica-safe operation locks."""

from contextlib import ExitStack
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.api.locking import OperationLockManager
from src.utils.config import override_settings


class _FakeRedisClient:
    """Small synchronized Redis substitute covering the lock Lua contracts."""

    def __init__(self):
        self._mutex = threading.Lock()
        self.writer = None
        self.readers = set()

    def ping(self):
        return True

    def set(self, _key, token, nx=False, px=None):
        del px
        with self._mutex:
            if nx and self.writer is not None:
                return False
            self.writer = token
            return True

    def eval(self, script, number_of_keys, *args):
        del number_of_keys
        with self._mutex:
            if script == OperationLockManager._ACQUIRE_READ:
                token = args[2]
                if self.writer is not None:
                    return 0
                self.readers.add(token)
                return 1
            if script == OperationLockManager._RELEASE_READ:
                self.readers.discard(args[1])
                return 1
            if script == OperationLockManager._ACTIVE_READERS:
                token = args[2]
                return len(self.readers) if self.writer == token else -1
            if script == OperationLockManager._RELEASE_WRITE:
                token = args[1]
                if self.writer == token:
                    self.writer = None
                    return 1
                return 0
        raise AssertionError("Unexpected Lua script")


class _FakeRedisFactory:
    client = _FakeRedisClient()

    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return cls.client


class OperationLockManagerTest(unittest.TestCase):
    def setUp(self):
        _FakeRedisFactory.client = _FakeRedisClient()
        fake_module = SimpleNamespace(Redis=_FakeRedisFactory, RedisError=RuntimeError)
        self.stack = ExitStack()
        self.stack.enter_context(patch("src.api.locking.redis", fake_module))
        self.stack.enter_context(override_settings(
            DISTRIBUTED_LOCK_ENABLED="true",
            DISTRIBUTED_LOCK_WAIT_SECONDS="2",
            DISTRIBUTED_LOCK_TTL_SECONDS="60",
        ))

    def tearDown(self):
        self.stack.close()

    def test_readers_can_run_concurrently_but_writer_waits(self):
        first_manager = OperationLockManager()
        second_manager = OperationLockManager()
        reader_entered = threading.Event()
        release_reader = threading.Event()
        writer_entered = threading.Event()

        def read_operation():
            with first_manager.read("course:12"):
                reader_entered.set()
                release_reader.wait(timeout=2)

        def write_operation():
            with second_manager.write("course:12"):
                writer_entered.set()

        reader = threading.Thread(target=read_operation)
        writer = threading.Thread(target=write_operation)
        reader.start()
        self.assertTrue(reader_entered.wait(timeout=1))
        writer.start()
        time.sleep(0.2)
        self.assertFalse(writer_entered.is_set())

        release_reader.set()
        reader.join(timeout=2)
        writer.join(timeout=2)
        self.assertTrue(writer_entered.is_set())


if __name__ == "__main__":
    unittest.main()
