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
    items: List[EvalItem] = []
    with open(Path(csv_path), "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            question = row["soal"]
            answer = row["jawaban"]
            nilai = float(row["nilai"])
            qid = "jk-" + question_key(question)
            digest = hashlib.sha256((qid + "\x00" + normalize_text(answer)).encode("utf-8")).hexdigest()
            items.append(EvalItem(
                item_id="jk-" + digest[:16],
                dataset="jk_case",
                question_id=qid,
                question=question,
                answer=answer,
                language="id",
                gold_label=case_study_label(nilai * 4),
                label_scale=3,
                split="case",
                reference_text=None,
                reference_document=str(reference_pdf),
                gold_score=nilai / MAX_POINTS,
            ))
    return items, {"rows": len(items), "questions": len({i.question_id for i in items})}


def load_jk_case_default(source: Path) -> Tuple[List[EvalItem], dict]:
    source = Path(source)
    return load_jk_case(source, source.parent / DEFAULT_REFERENCE_NAME)
