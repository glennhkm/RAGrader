"""Private Indonesian case-study adapter (columns ``soal, jawaban, nilai``; nilai 0-25)."""

import csv
import hashlib
from pathlib import Path
from typing import List, Tuple

from src.evaluation.datasets.engsaf import normalize_text, question_key
from src.evaluation.schema import EvalItem
from src.evaluation.thresholds import case_study_label

DEFAULT_REFERENCE_NAME = "Kunci Jawaban Jaringan Komputer.pdf"
MAX_POINTS = 25


def load_jk_case(csv_path: Path, reference_pdf: Path) -> Tuple[List[EvalItem], dict]:
    """Items reference the PDF by file name plus content sha256, never by an absolute path,
    so the snapshot is the same on every machine and changes when the PDF does."""
    reference_pdf = Path(reference_pdf)
    reference_sha256 = hashlib.sha256(reference_pdf.read_bytes()).hexdigest()
    items: List[EvalItem] = []
    seen = set()
    rows_read = 0
    with open(Path(csv_path), "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows_read += 1
            question = row["soal"]
            answer = row["jawaban"]
            nilai = float(row["nilai"])
            qid = "jk-" + question_key(question)
            digest = hashlib.sha256((qid + "\x00" + normalize_text(answer)).encode("utf-8")).hexdigest()
            item_id = "jk-" + digest[:16]
            if item_id in seen:
                continue  # identical normalised answer to the same question: keep the first
            seen.add(item_id)
            items.append(EvalItem(
                item_id=item_id,
                dataset="jk_case",
                question_id=qid,
                question=question,
                answer=answer,
                language="id",
                gold_label=case_study_label(nilai * 4),
                label_scale=3,
                split="case",
                reference_text=None,
                reference_document=reference_pdf.name,
                reference_sha256=reference_sha256,
                gold_score=nilai / MAX_POINTS,
            ))
    return items, {"rows": len(items), "rows_read": rows_read,
                   "duplicates_dropped": rows_read - len(items),
                   "questions": len({i.question_id for i in items})}


def load_jk_case_default(source: Path) -> Tuple[List[EvalItem], dict]:
    source = Path(source)
    return load_jk_case(source, source.parent / DEFAULT_REFERENCE_NAME)
