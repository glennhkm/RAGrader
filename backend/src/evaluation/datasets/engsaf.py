"""EngSAF adapter. Reads the CSV and applies the documented cleaning rules (spec 6.2)."""

import csv
import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from src.evaluation.schema import EvalItem


def normalize_text(s: str) -> str:
    """Casefold, collapse whitespace runs, strip."""
    return " ".join((s or "").casefold().split())


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def question_key(question: str) -> str:
    return _sha(normalize_text(question))[:12]


@dataclass
class CleaningReport:
    rows_read: int = 0
    empty_dropped: int = 0
    duplicate_groups_collapsed: int = 0
    duplicate_rows_removed: int = 0
    conflicting_groups_dropped: int = 0
    conflicting_rows_dropped: int = 0
    multi_reference_questions: int = 0
    questions: int = 0
    items: int = 0


def load_engsaf(csv_path: Path) -> Tuple[List[EvalItem], CleaningReport]:
    report = CleaningReport()
    # (question_id, normalized answer) -> list of row dicts, in file order
    groups: "OrderedDict[Tuple[str, str], List[dict]]" = OrderedDict()
    references: Dict[str, "OrderedDict[str, str]"] = {}

    with open(Path(csv_path), "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            report.rows_read += 1
            answer = row.get("Student Answer") or ""
            if not normalize_text(answer):
                report.empty_dropped += 1
                continue
            question = row.get("Question") or ""
            qid = "engsaf-" + question_key(question)
            reference = row.get("Correct Answer") or ""
            refs = references.setdefault(qid, OrderedDict())
            refs.setdefault(normalize_text(reference), reference)
            groups.setdefault((qid, normalize_text(answer)), []).append(
                {
                    "question": question,
                    "answer": answer,
                    "label": int(float(row["output_label"])),
                    "qid": qid,
                }
            )

    report.multi_reference_questions = sum(1 for r in references.values() if len(r) > 1)

    items: List[EvalItem] = []
    for (qid, norm_answer), rows in groups.items():
        if len({r["label"] for r in rows}) > 1:
            report.conflicting_groups_dropped += 1
            report.conflicting_rows_dropped += len(rows)
            continue
        if len(rows) > 1:
            report.duplicate_groups_collapsed += 1
            report.duplicate_rows_removed += len(rows) - 1
        first = rows[0]
        items.append(
            EvalItem(
                item_id="engsaf-" + _sha(qid + "\x00" + norm_answer)[:16],
                dataset="engsaf",
                question_id=qid,
                question=first["question"],
                answer=first["answer"],
                language="en",
                gold_label=first["label"],
                label_scale=3,
                split="",
                reference_text=next(iter(references[qid].values())),
            )
        )

    report.questions = len({i.question_id for i in items})
    report.items = len(items)
    return items, report
