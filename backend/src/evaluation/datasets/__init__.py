"""Dataset loaders and the ``load_dataset`` dispatcher.

Later tasks register ``scientsbank``, ``jk_case`` and ``synthetic`` in ``_LOADERS``.
"""

import dataclasses
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from src.evaluation.datasets.engsaf import load_engsaf
from src.evaluation.datasets.jk_case import load_jk_case_default
from src.evaluation.datasets.scientsbank import load_scientsbank
from src.evaluation.datasets.synthetic import load_synthetic
from src.evaluation.schema import EvalItem


def _load_engsaf(source: Path) -> Tuple[List[EvalItem], dict]:
    items, report = load_engsaf(source)
    return items, dataclasses.asdict(report)


_LOADERS: Dict[str, Callable[[Optional[Path]], Tuple[List[EvalItem], dict]]] = {
    "engsaf": _load_engsaf,
    "scientsbank": load_scientsbank,
    "jk_case": load_jk_case_default,
    "synthetic": lambda source: load_synthetic() if source is None else load_synthetic(source),
}


def load_dataset(name: str, source: Optional[Path]) -> Tuple[List[EvalItem], dict]:
    if name not in _LOADERS:
        raise KeyError("Unknown dataset: %s" % name)
    return _LOADERS[name](None if source is None else Path(source))
