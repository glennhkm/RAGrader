import tempfile
import unittest
from pathlib import Path

from src.evaluation import datasets
from src.evaluation.datasets.engsaf import load_engsaf, normalize_text, question_key

# Invented text only. Never place real EngSAF rows here.
CSV_TEXT = (
    "Question_id,Question,Student Answer,Correct Answer,output_label,feedback\n"
    ",Define latency?,Delay between request and response.,Latency is delay.,2,ok\n"
    "3.0,Define latency?,It is the time a packet takes.,Latency is delay.,1.0,meh\n"
    "3,Define latency?,   ,Latency is delay.,0,empty\n"
    "7,Explain caching.,Stores copies.,Caching keeps copies.,2,a\n"
    "7,Explain caching.,stores   copies.,Caching keeps copies.,2,b\n"
    "7,Explain caching.,STORES COPIES.,Caching keeps copies.,2.0,c\n"
    "9,What is jitter?,Variation.,Jitter is variance.,1,x\n"
    "9,What is jitter?,VARIATION.,Jitter is variance.,0,y\n"
    "11,Two refs question?,Answer one.,First reference.,2,p\n"
    "11,Two refs question?,Answer two.,Second reference.,0,q\n"
)


class EngsafTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.csv = Path(self._tmp.name) / "fake.csv"
        self.csv.write_text(CSV_TEXT, encoding="utf-8", newline="")

    def test_blank_and_float_question_ids_share_cluster(self):
        items, _ = load_engsaf(self.csv)
        qids = {i.question_id for i in items if i.question.startswith("Define latency")}
        self.assertEqual(1, len(qids))

    def test_cleaning_counts(self):
        items, rep = load_engsaf(self.csv)
        self.assertEqual(
            (1, 1, 2, 1, 2),
            (rep.empty_dropped, rep.duplicate_groups_collapsed, rep.duplicate_rows_removed,
             rep.conflicting_groups_dropped, rep.conflicting_rows_dropped),
        )
        self.assertEqual(1, rep.multi_reference_questions)
        self.assertEqual(10, rep.rows_read)
        self.assertEqual(3, rep.questions)
        self.assertEqual(len(items), rep.items)

    def test_first_reference_answer_is_used(self):
        items, _ = load_engsaf(self.csv)
        refs = {i.reference_text for i in items if i.question.startswith("Two refs")}
        self.assertEqual({"First reference."}, refs)

    def test_item_ids_stable_and_unique(self):
        a, _ = load_engsaf(self.csv)
        b, _ = load_engsaf(self.csv)
        self.assertEqual([i.item_id for i in a], [i.item_id for i in b])
        self.assertEqual(len(a), len({i.item_id for i in a}))

    def test_item_fields_and_first_row_text_kept(self):
        items, _ = load_engsaf(self.csv)
        cache = [i for i in items if i.question.startswith("Explain caching")]
        self.assertEqual(1, len(cache))
        item = cache[0]
        self.assertEqual("Stores copies.", item.answer)
        self.assertEqual(2, item.gold_label)
        self.assertEqual(3, item.label_scale)
        self.assertEqual("en", item.language)
        self.assertEqual("", item.split)
        self.assertEqual("engsaf", item.dataset)
        self.assertEqual("engsaf-" + question_key(item.question), item.question_id)

    def test_normalize_text(self):
        self.assertEqual("a b", normalize_text("  A \n  B "))

    def test_dispatcher(self):
        items, info = datasets.load_dataset("engsaf", self.csv)
        self.assertEqual(5, len(items))
        self.assertEqual(10, info["rows_read"])
        with self.assertRaises(KeyError):
            datasets.load_dataset("nope", self.csv)


if __name__ == "__main__":
    unittest.main()
