"""Public hand-written synthetic smoke set (30 items, 6 questions)."""

from pathlib import Path
from typing import List, Tuple

from src.evaluation.paths import EVAL_ASSETS
from src.evaluation.schema import EvalItem, read_items

DEFAULT_PATH = EVAL_ASSETS / "synthetic" / "items.jsonl"


def load_synthetic(path: Path = DEFAULT_PATH) -> Tuple[List[EvalItem], dict]:
    items = read_items(Path(path))
    return items, {"items": len(items), "questions": len({i.question_id for i in items})}
