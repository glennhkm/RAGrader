import tempfile
import unittest
from pathlib import Path

from src.evaluation import paths
from src.evaluation.schema import (
    EvalItem, EvalResult, is_private, read_items, read_results, write_jsonl, append_jsonl,
)


class SchemaTest(unittest.TestCase):
    def test_item_round_trip_jsonl(self):
        item = EvalItem("i1", "synthetic", "q1", "Q?", "A.", "en", 2, 3, "smoke", reference_text="R")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "items.jsonl"
            write_jsonl(p, [item])
            self.assertEqual([item], read_items(p))

    def test_result_tuples_survive_round_trip(self):
        r = EvalResult("i1", "h", "synthetic", "q1", "smoke", 2, True, 80.0, 0.9,
                       integrity_warnings=("a",), retrieved_sources=("q-1.txt", "q-2.txt"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            append_jsonl(p, r)
            append_jsonl(p, r)
            self.assertEqual([r, r], read_results(p))

    def test_partial_trailing_line_ignored(self):
        r = EvalResult("i1", "h", "synthetic", "q1", "smoke", 2, True, 80.0, 0.9)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            append_jsonl(p, r)
            with open(p, "a", encoding="utf-8") as f:
                f.write('{"item_id": "i2", "conf')
            self.assertEqual([r], read_results(p))

    def test_registry_visibility(self):
        self.assertTrue(is_private("engsaf"))
        self.assertTrue(is_private("jk_case"))
        self.assertFalse(is_private("scientsbank"))
        self.assertFalse(is_private("synthetic"))
        with self.assertRaises(KeyError):
            is_private("beetle")

    def test_is_private_path_rejects_traversal(self):
        self.assertTrue(paths.is_private_path(paths.PRIVATE_DIR / "evaluation" / "x.jsonl"))
        self.assertFalse(paths.is_private_path(paths.PRIVATE_DIR / ".." / "docs" / "x.jsonl"))
        self.assertFalse(paths.is_private_path(paths.REPORTS_DIR / "x.json"))
