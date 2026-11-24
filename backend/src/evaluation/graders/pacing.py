"""Request pacing shared by the LLM and embedding calls of one in-process grader."""

import threading
import time
from typing import Callable


class RateLimiter:
    """Spaces calls at least ``60 / requests_per_minute`` seconds apart, across threads.

    Retries made inside a provider SDK are not seen here, so leave some headroom.
    """

    def __init__(self, requests_per_minute: float,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self._gap = 60.0 / requests_per_minute
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            at = max(now, self._next)
            self._next = at + self._gap
        if at > now:
            self._sleep(at - now)
