import hashlib
import tempfile
import unittest
from pathlib import Path

from src.evaluation.materials import (
    MaterialDoc,
    build_materials,
    gold_source,
    source_name,
    write_materials,
)
from src.evaluation.schema import EvalItem


def _item(iid, qid, split="dev", role="eval", ref="ref", question="Q?", **kw):
    return EvalItem(iid, "engsaf", qid, question, "ans", "en", 1, 3, split,
                    role=role, reference_text=ref, **kw)


class MaterialsTest(unittest.TestCase):
    def test_source_name_is_hashed(self):
        expected = "q-" + hashlib.sha256(b"q1").hexdigest()[:12] + ".txt"
        self.assertEqual(expected, source_name("q1"))
        self.assertNotIn("q1", source_name("q1")[2:-4])

    def test_one_document_per_question_across_splits_and_roles(self):
        items = [
            _item("a", "q1", "dev", ref="R1", question="Q1"),
            _item("b", "q1", "dev", ref="R1", question="Q1"),
            _item("c", "q2", "test", ref="R2", question="Q2"),
            _item("d", "q3", "dev", role="bank", ref="R3", question="Q3"),
        ]
        docs = build_materials(items)
        self.assertEqual(3, len(docs))
        self.assertEqual([d.source for d in docs], sorted(d.source for d in docs))
        by = {d.source: d.text for d in docs}
        self.assertEqual("Question: Q1\nReference answer: R1", by[source_name("q1")])
        self.assertIn("R2", by[source_name("q2")])
        self.assertNotIn("R1", by[source_name("q2")])
        self.assertNotIn("R2", by[source_name("q1")])

    def test_conflicting_reference_uses_first_sorted_item_id(self):
        items = [_item("z", "q1", ref="LATE"), _item("a", "q1", ref="EARLY")]
        for order in (items, items[::-1]):
            docs = build_materials(order)
            self.assertEqual(1, len(docs))
            self.assertIn("EARLY", docs[0].text)

    def test_gold_source_matches_written_filename(self):
        items = [_item("a", "q1"), _item("b", "q2", ref="R2")]
        with tempfile.TemporaryDirectory() as d:
            paths = write_materials(build_materials(items), Path(d) / "sub")
            names = {p.name for p in paths}
            for it in items:
                self.assertIn(gold_source(it), names)
            self.assertEqual(
                "Question: Q?\nReference answer: ref",
                (Path(d) / "sub" / source_name("q1")).read_text(encoding="utf-8"))

    def test_pdf_reference_yields_single_document(self):
        with tempfile.TemporaryDirectory() as d:
            pdf = Path(d) / "case.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            items = [
                EvalItem(f"i{k}", "jk_case", f"q{k}", "Q", "a", "id", 1, 3, "case",
                         reference_text=None, reference_document=str(pdf))
                for k in range(3)
            ]
            docs = build_materials(items)
            self.assertEqual(1, len(docs))
            self.assertEqual("case.pdf", docs[0].source)
            self.assertEqual("", docs[0].text)
            self.assertEqual(str(pdf), docs[0].path)
            self.assertEqual("case.pdf", gold_source(items[0]))
            out = Path(d) / "out"
            paths = write_materials(docs, out)
            self.assertEqual([out / "case.pdf"], paths)
            self.assertEqual(b"%PDF-1.4 fake", paths[0].read_bytes())

    def test_write_returns_paths_in_doc_order_utf8(self):
        docs = [MaterialDoc("b.txt", "café"), MaterialDoc("a.txt", "x")]
        with tempfile.TemporaryDirectory() as d:
            paths = write_materials(docs, Path(d) / "n" / "m")
            self.assertEqual(["b.txt", "a.txt"], [p.name for p in paths])
            self.assertEqual("café", paths[0].read_text(encoding="utf-8"))
