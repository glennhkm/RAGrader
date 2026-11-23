"""Dataset loaders and the ``load_dataset`` dispatcher.

Later tasks register ``scientsbank``, ``jk_case`` and ``synthetic`` in ``_LOADERS``.
"""

import dataclasses
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from src.evaluation.datasets.engsaf import load_engsaf
from src.evaluation.schema import EvalItem


def _load_engsaf(source: Path) -> Tuple[List[EvalItem], dict]:
    items, report = load_engsaf(source)
    return items, dataclasses.asdict(report)


_LOADERS: Dict[str, Callable[[Path], Tuple[List[EvalItem], dict]]] = {
    "engsaf": _load_engsaf,
}


def load_dataset(name: str, source: Path) -> Tuple[List[EvalItem], dict]:
    if name not in _LOADERS:
        raise KeyError("Unknown dataset: %s" % name)
    return _LOADERS[name](Path(source))
