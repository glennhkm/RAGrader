"""Filesystem locations used by the evaluation harness."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
PRIVATE_DIR = REPO_ROOT / "private-data"
EVAL_ASSETS = BACKEND_DIR / "evaluation"
REPORTS_DIR = REPO_ROOT / "docs" / "evaluation"


def is_private_path(p: Path) -> bool:
    """True only when ``p`` resolves (symlinks and ``..`` followed) inside PRIVATE_DIR."""
    try:
        Path(p).resolve().relative_to(PRIVATE_DIR.resolve())
    except ValueError:
        return False
    return True
