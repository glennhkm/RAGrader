"""Cross-container operation locks for consistent course data access."""

from contextlib import contextmanager
import hashlib
import os
from threading import RLock
import time
from typing import Any, Iterator, Optional
import uuid

from loguru import logger

try:
    import redis
except ImportError:  # Local single-process development does not require Redis.
    redis = None


class LockAcquisitionError(RuntimeError):
    """Raised when a shared operation lock cannot be acquired safely."""


class OperationLockManager:
    """Provide local locks or Redis-backed read/write locks per resource.

    Read locks can coexist, allowing grading requests for the same course to be
    distributed across replicas. A write lock blocks new readers and waits for
    active readers, making material upload/delete/clear operations exclusive.
    """

    _ACQUIRE_READ = """
        local now = redis.call('TIME')
        local nowms = (now[1] * 1000) + math.floor(now[2] / 1000)
        redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', nowms)
        if redis.call('EXISTS', KEYS[1]) == 0 then
            redis.call('ZADD', KEYS[2], nowms + ARGV[2], ARGV[1])
            redis.call('PEXPIRE', KEYS[2], ARGV[2])
            return 1
        end
        return 0
    """

    _RELEASE_READ = """
        redis.call('ZREM', KEYS[1], ARGV[1])
        if redis.call('ZCARD', KEYS[1]) == 0 then
            redis.call('DEL', KEYS[1])
        end
        return 1
    """

    _ACTIVE_READERS = """
        if redis.call('GET', KEYS[1]) ~= ARGV[1] then
            return -1
        end
        redis.call('PEXPIRE', KEYS[1], ARGV[2])
        local now = redis.call('TIME')
        local nowms = (now[1] * 1000) + math.floor(now[2] / 1000)
        redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', nowms)
        return redis.call('ZCARD', KEYS[2])
    """

    _RELEASE_WRITE = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
    """

    def __init__(self) -> None:
        self._local_lock = RLock()
        self.enabled = os.getenv("DISTRIBUTED_LOCK_ENABLED", "false").lower() in {
            "1", "true", "yes", "on",
        }
        self._redis: Optional[Any] = None
        self._prefix = os.getenv("DISTRIBUTED_LOCK_PREFIX", "airag:lock")
        self._lease_ms = max(60, int(os.getenv("DISTRIBUTED_LOCK_TTL_SECONDS", "900"))) * 1000
        self._wait_seconds = max(1, int(os.getenv("DISTRIBUTED_LOCK_WAIT_SECONDS", "120")))
        self._poll_seconds = 0.1

        if self.enabled:
            if redis is None:
                raise RuntimeError(
                    "Distributed locking is enabled but the redis package is not installed"
                )
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            self._redis = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30,
            )
            try:
                self._redis.ping()
            except redis.RedisError as exc:
                raise RuntimeError("Distributed locking is enabled but Redis is unavailable") from exc
            logger.info("Distributed Redis read/write locks enabled")
        else:
            logger.info("Distributed locks disabled; using a process-local lock")

    def ping(self) -> bool:
        """Return whether the configured lock backend is reachable."""
        if not self.enabled:
            return True
        assert self._redis is not None
        return bool(self._redis.ping())

    def _keys(self, resource: str) -> tuple[str, str]:
        digest = hashlib.sha256(resource.encode("utf-8")).hexdigest()
        base = f"{self._prefix}:{digest}"
        return f"{base}:writer", f"{base}:readers"

    def _wait_or_raise(self, deadline: float, resource: str, mode: str) -> None:
        if time.monotonic() >= deadline:
            raise LockAcquisitionError(
                f"Timed out waiting for {mode} access to {resource}"
            )
        time.sleep(self._poll_seconds)

    @contextmanager
    def read(self, resource: str) -> Iterator[None]:
        """Acquire shared read access for one course or logical resource."""
        with self._local_lock:
            if not self.enabled:
                yield
                return

            assert self._redis is not None
            writer_key, readers_key = self._keys(resource)
            token = uuid.uuid4().hex
            deadline = time.monotonic() + self._wait_seconds
            try:
                while not self._redis.eval(
                    self._ACQUIRE_READ,
                    2,
                    writer_key,
                    readers_key,
                    token,
                    self._lease_ms,
                ):
                    self._wait_or_raise(deadline, resource, "read")
                yield
            except redis.RedisError as exc:
                raise LockAcquisitionError("Redis failed while acquiring a read lock") from exc
            finally:
                try:
                    self._redis.eval(self._RELEASE_READ, 1, readers_key, token)
                except redis.RedisError:
                    logger.exception("Failed to release distributed read lock")

    @contextmanager
    def write(self, resource: str) -> Iterator[None]:
        """Acquire exclusive write access for one course or logical resource."""
        with self._local_lock:
            if not self.enabled:
                yield
                return

            assert self._redis is not None
            writer_key, readers_key = self._keys(resource)
            token = uuid.uuid4().hex
            deadline = time.monotonic() + self._wait_seconds
            acquired = False
            try:
                while not acquired:
                    acquired = bool(self._redis.set(
                        writer_key,
                        token,
                        nx=True,
                        px=self._lease_ms,
                    ))
                    if not acquired:
                        self._wait_or_raise(deadline, resource, "write")

                while True:
                    readers = int(self._redis.eval(
                        self._ACTIVE_READERS,
                        2,
                        writer_key,
                        readers_key,
                        token,
                        self._lease_ms,
                    ))
                    if readers == 0:
                        break
                    if readers < 0:
                        raise LockAcquisitionError("Distributed write-lock lease was lost")
                    self._wait_or_raise(deadline, resource, "write")
                yield
            except redis.RedisError as exc:
                raise LockAcquisitionError("Redis failed while acquiring a write lock") from exc
            finally:
                if acquired:
                    try:
                        self._redis.eval(self._RELEASE_WRITE, 1, writer_key, token)
                    except redis.RedisError:
                        logger.exception("Failed to release distributed write lock")
