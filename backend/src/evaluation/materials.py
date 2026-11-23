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


def gold_source(item: EvalItem) -> str:
    if item.reference_text is None and item.reference_document:
        return Path(item.reference_document).name
    return source_name(item.question_id)


def build_materials(items: Sequence[EvalItem]) -> List[MaterialDoc]:
    """One document per distinct question (all splits and roles), sorted by source."""
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
                docs[source] = MaterialDoc(source, "", item.reference_document)
    return [docs[s] for s in sorted(docs)]


def write_materials(docs: Sequence[MaterialDoc], directory: Path) -> List[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    out: List[Path] = []
    for doc in docs:
        target = directory / doc.source
        if doc.path:
            shutil.copyfile(doc.path, target)
        else:
            target.write_text(doc.text, encoding="utf-8")
        out.append(target)
    return out
