import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from src.evaluation import datasets
from src.evaluation.datasets.engsaf import normalize_text, question_key
from src.evaluation.datasets.jk_case import load_jk_case
from src.evaluation.datasets.synthetic import load_synthetic

Q = "Jelaskan fungsi router dalam jaringan komputer."


class SmallDatasetsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = Path(self.tmp.name) / "fixture.csv"
        rows = [("8", "Router adalah kabel."), ("9", "Router menghubungkan dua jaringan."),
                ("17.0", "Router meneruskan paket antar jaringan memakai tabel routing."),
                ("18", "Router memilih rute terbaik dan meneruskan paket ke jaringan tujuan."),
                ("25", "Router meneruskan paket berdasarkan alamat IP tujuan dan tabel routing.")]
        with open(self.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["soal", "jawaban", "nilai"])
            for n, a in rows:
                w.writerow([Q, a, n])

    def test_jk_case_conversion_uses_teacher_rule(self):
        items, _ = load_jk_case(self.csv, Path("key.pdf"))
        self.assertEqual([0, 1, 1, 2, 2], [i.gold_label for i in items])
        self.assertEqual({"case"}, {i.split for i in items})
        self.assertAlmostEqual(18 / 25, items[3].gold_score)
        self.assertAlmostEqual(17 / 25, items[2].gold_score)

    def test_jk_case_fields(self):
        items, _ = load_jk_case(self.csv, Path("key.pdf"))
        it = items[0]
        qid = "jk-" + question_key(Q)
        self.assertEqual(qid, it.question_id)
        digest = hashlib.sha256((qid + "\x00" + normalize_text("Router adalah kabel.")).encode("utf-8")).hexdigest()
        self.assertEqual("jk-" + digest[:16], it.item_id)
        self.assertEqual(("id", 3, "jk_case", "key.pdf", None), (it.language, it.label_scale, it.dataset, it.reference_document, it.reference_text))
        self.assertEqual(5, len({i.item_id for i in items}))

    def test_jk_case_drops_duplicate_normalised_answers(self):
        with open(self.csv, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([Q, "  ROUTER adalah   kabel. ", "3"])   # same after normalisation
            w.writerow([Q, "Router adalah kabel.", "8"])        # exact duplicate
        items, report = load_jk_case(self.csv, Path("key.pdf"))
        self.assertEqual(5, len(items))
        self.assertEqual(5, len({i.item_id for i in items}))
        self.assertEqual(0, items[0].gold_label)  # the first row is kept
        self.assertEqual(2, report["duplicates_dropped"])
        self.assertEqual(7, report["rows_read"])

    def test_dispatcher_defaults_reference_pdf_beside_csv(self):
        items, _ = datasets.load_dataset("jk_case", self.csv)
        self.assertEqual(str(self.csv.parent / "Kunci Jawaban Jaringan Komputer.pdf"), items[0].reference_document)

    def test_synthetic_set_shape(self):
        items, _ = load_synthetic()
        self.assertEqual(30, len(items))
        by_q = {}
        for i in items:
            by_q.setdefault(i.question_id, set()).add(i.gold_label)
        self.assertEqual(6, len(by_q))
        self.assertTrue(all({0, 1, 2} <= labels for labels in by_q.values()))
        self.assertEqual({"smoke"}, {i.split for i in items})
        self.assertEqual(30, len({i.item_id for i in items}))
        self.assertTrue(all(i.reference_text and i.language == "en" for i in items))

    def test_dispatcher_synthetic_default(self):
        items, _ = datasets.load_dataset("synthetic", None)
        self.assertEqual(30, len(items))
