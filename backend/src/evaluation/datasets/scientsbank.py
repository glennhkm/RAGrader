"""SciEntsBank adapter: pinned HF download, checksum verification, label mapping.

Source: HF ``nkazi/SciEntsBank`` (Nielsen et al., 2008; CC BY 4.0), pinned to one revision.
"""

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Tuple

from src.evaluation.datasets.engsaf import question_key
from src.evaluation.schema import EvalItem

REVISION = "abaadf77345c5d68b73b630131a8ae164a45f3ab"
URL_TEMPLATE = "https://huggingface.co/datasets/nkazi/SciEntsBank/resolve/{revision}/{path}"
FILES: Dict[str, Tuple[str, str]] = {
    "train": ("data/train-00001.parquet", "b7c65a6b0e3df49b4f7d38a7223ebaea0e17010608309b66af84322da7cb61a7"),
    "test_ua": ("data/test-ua-00001.parquet", "a3d28086020d40f68ba2b1b543b97463518aea41bf0afbc27f03bcbd4abafe42"),
    "test_uq": ("data/test-uq-00001.parquet", "0657311e80f0eb61323d1b88ac863605b28ab1aeaf386caf4419a6f48160426a"),
}
LABEL_NAMES = ("correct", "contradictory", "partially_correct_incomplete", "irrelevant", "non_domain")
ORDINAL = {
    "correct": 2,
    "partially_correct_incomplete": 1,
    "contradictory": 0,
    "irrelevant": 0,
    "non_domain": 0,
}
# The official train split is dev.
SPLIT_MAP = {"train": "dev", "test_ua": "test_ua", "test_uq": "test_uq"}


def _httpx_get(url: str) -> bytes:
    import httpx

    response = httpx.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    return response.content


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(cache_dir: Path, http_get: Callable[[str], bytes] = _httpx_get) -> Dict[str, Path]:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, Path] = {}
    for split, (path, sha) in FILES.items():
        target = cache_dir / ("%s.parquet" % split)
        if target.exists():
            if _sha256_file(target) == sha:
                paths[split] = target
                continue
            target.unlink()
        data = http_get(URL_TEMPLATE.format(revision=REVISION, path=path))
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError(f"checksum mismatch for {path}")
        fd, tmp_name = tempfile.mkstemp(dir=str(cache_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        paths[split] = target
    return paths


def read_parquet_rows(path: Path) -> List[dict]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pip install -r requirements-eval.txt") from exc
    return pq.read_table(str(path)).to_pylist()


def rows_to_items(rows: Iterable[dict], split: str) -> List[EvalItem]:
    item_split = SPLIT_MAP[split]
    items = []
    for row in rows:
        raw = LABEL_NAMES[row["label"]]
        items.append(EvalItem(
            item_id="scientsbank-" + str(row["id"]),
            dataset="scientsbank",
            question_id="scientsbank-" + question_key(row["question"]),
            question=row["question"],
            answer=row["student_answer"],
            language="en",
            gold_label=ORDINAL[raw],
            label_scale=3,
            split=item_split,
            reference_text=row["reference_answer"],
            gold_label_raw=raw,
        ))
    return items


def load_scientsbank(cache_dir: Path) -> Tuple[List[EvalItem], dict]:
    paths = download(Path(cache_dir))
    items: List[EvalItem] = []
    counts: Dict[str, int] = {}
    for split in FILES:
        split_items = rows_to_items(read_parquet_rows(paths[split]), split)
        counts[split] = len(split_items)
        items.extend(split_items)
    provenance = {
        "revision": REVISION,
        "files": {split: sha for split, (_, sha) in FILES.items()},
        "counts": counts,
    }
    return items, provenance
