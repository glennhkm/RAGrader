import tempfile
import unittest
from pathlib import Path

from src.evaluation import datasets
from src.evaluation.datasets.scientsbank import (
    FILES,
    REVISION,
    download,
    load_scientsbank,
    rows_to_items,
)
from src.evaluation.datasets.engsaf import question_key


class ScientsbankTest(unittest.TestCase):
    def test_label_mapping_is_three_way(self):
        rows = [{"id": f"x{i}", "question": "Q", "reference_answer": "R", "student_answer": "A", "label": i} for i in range(5)]
        items = rows_to_items(rows, "train")
        self.assertEqual([2, 0, 1, 0, 0], [i.gold_label for i in items])
        self.assertEqual("partially_correct_incomplete", items[2].gold_label_raw)

    def test_item_fields_and_split_mapping(self):
        row = {"id": "a1", "question": "What? ", "reference_answer": "Ref", "student_answer": "Ans", "label": 0}
        item = rows_to_items([row], "train")[0]
        self.assertEqual("dev", item.split)
        self.assertEqual("scientsbank-a1", item.item_id)
        self.assertEqual("scientsbank-" + question_key("What? "), item.question_id)
        self.assertEqual(("Ref", "Ans", "en", 3, "scientsbank"),
                         (item.reference_text, item.answer, item.language, item.label_scale, item.dataset))
        self.assertEqual("test_ua", rows_to_items([row], "test_ua")[0].split)
        self.assertEqual("test_uq", rows_to_items([row], "test_uq")[0].split)

    def test_download_rejects_bad_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                download(Path(d), http_get=lambda url: b"not parquet")
            self.assertEqual([], list(Path(d).rglob("*.parquet")))

    def test_download_urls_are_revision_pinned(self):
        seen = []
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                download(Path(d), http_get=lambda url: seen.append(url) or b"x")
        self.assertTrue(all(f"/resolve/{REVISION}/data/" in u for u in seen))

    def test_registered_in_dispatcher(self):
        self.assertIn("scientsbank", datasets._LOADERS)
        self.assertEqual(3, len(FILES))


if __name__ == "__main__":
    unittest.main()
