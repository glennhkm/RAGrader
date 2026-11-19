"""Process runtime (grader + shared locks) owned by the FastAPI lifespan.

Nothing here is created at import time. ``create_app()`` builds the runtime
during application startup (or receives one injected by tests) and registers
it with ``set_runtime()``; request handlers reach it through ``get_runtime()``.
"""

import copy
from dataclasses import dataclass
from threading import Lock
from typing import Any, Optional

from loguru import logger

from ..grading import EssayGrader
from ..utils.config import Settings, get_settings
from .locking import OperationLockManager


@dataclass
class AppRuntime:
    """Long-lived services shared by every request in one API process."""

    grader: Any  # EssayGrader (duck-typed so tests can inject fakes)
    operation_locks: Any  # OperationLockManager
    settings: Settings


_runtime: Optional[AppRuntime] = None
_runtime_lock = Lock()


def build_runtime(settings: Optional[Settings] = None) -> AppRuntime:
    """Construct the grader and lock manager from settings.

    Raises whatever the underlying services raise (e.g. Chroma or Redis being
    unreachable) so that application startup fails loudly.
    """
    settings = settings or get_settings()
    # The grader/pipeline mutate their config (e.g. switching embedding
    # models), so give them a private copy of the resolved YAML.
    config = copy.deepcopy(dict(settings.raw))
    grader = EssayGrader(
        config,
        provider=settings.llm.provider,
        model_name=settings.llm.model,
        settings=settings,
    )
    operation_locks = OperationLockManager(settings.locks)
    logger.info("API runtime initialized")
    return AppRuntime(grader=grader, operation_locks=operation_locks, settings=settings)


def set_runtime(runtime: Optional[AppRuntime]) -> None:
    """Register (or clear with ``None``) the active runtime."""
    global _runtime
    with _runtime_lock:
        _runtime = runtime


def get_runtime() -> AppRuntime:
    """Return the active runtime.

    Raises:
        RuntimeError: if the application has not completed startup.
    """
    runtime = _runtime
    if runtime is None:
        raise RuntimeError("API runtime not initialized; the application has not started")
    return runtime


def is_runtime_ready() -> bool:
    """Whether a runtime is registered."""
    return _runtime is not None
