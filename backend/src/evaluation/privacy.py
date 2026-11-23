"""Privacy guard (spec section 6.7): per-item output of private datasets stays in private-data/."""

from pathlib import Path
from typing import Iterable

from .paths import is_private_path
from .schema import is_private


class PrivacyError(RuntimeError):
    """A private dataset's per-item output would be written outside ``private-data/``."""


def assert_output_allowed(datasets: Iterable[str], out_dir: Path) -> None:
    private = sorted(ds for ds in datasets if is_private(ds))
    if private and not is_private_path(Path(out_dir)):
        raise PrivacyError(
            f"per-item output for private datasets {private} must be written under "
            "private-data/")
