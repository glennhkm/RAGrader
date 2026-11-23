"""Per-question reference answers rendered as course materials (no vector store)."""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.evaluation.schema import EvalItem


def source_name(question_id: str) -> str:
    """Hashed filename so question ids stay out of the vector store and logs."""
    return "q-" + hashlib.sha256(question_id.encode("utf-8")).hexdigest()[:12] + ".txt"


@dataclass(frozen=True)
class MaterialDoc:
    source: str
    text: str
    path: Optional[str] = None  # source PDF path for document references
    sha256: Optional[str] = None  # expected content hash of ``path``, checked when written


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def resolve_reference(reference: str, reference_dir: Optional[Path]) -> str:
    """An absolute reference is used as is; a bare name lives in ``reference_dir``."""
    p = Path(reference)
    if p.is_absolute() or reference_dir is None:
        return str(p)
    return str(Path(reference_dir) / p)


def gold_source(item: EvalItem) -> str:
    if item.reference_text is None and item.reference_document:
        return Path(item.reference_document).name
    return source_name(item.question_id)


def build_materials(items: Sequence[EvalItem],
                    reference_dir: Optional[Path] = None) -> List[MaterialDoc]:
    """One document per distinct question (all splits and roles), sorted by source.

    Document references (the case-study PDF) are resolved against ``reference_dir``.
    """
    docs: Dict[str, MaterialDoc] = {}
    for item in sorted(items, key=lambda i: i.item_id):
        if item.reference_text is not None:
            source = source_name(item.question_id)
            if source not in docs:
                text = f"Question: {item.question}\nReference answer: {item.reference_text}"
                docs[source] = MaterialDoc(source, text)
        elif item.reference_document:
            source = Path(item.reference_document).name
            if source not in docs:
                docs[source] = MaterialDoc(
                    source, "", resolve_reference(item.reference_document, reference_dir),
                    item.reference_sha256)
    return [docs[s] for s in sorted(docs)]


def write_materials(docs: Sequence[MaterialDoc], directory: Path) -> List[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    out: List[Path] = []
    for doc in docs:
        target = directory / doc.source
        if doc.path:
            if doc.sha256 is not None and _sha256_file(Path(doc.path)) != doc.sha256:
                raise ValueError("reference document checksum mismatch; prepare the "
                                 "dataset again")
            shutil.copyfile(doc.path, target)
        else:
            target.write_text(doc.text, encoding="utf-8")
        out.append(target)
    return out
