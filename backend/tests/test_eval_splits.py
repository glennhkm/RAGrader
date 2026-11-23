import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from src.evaluation.schema import EvalItem
from src.evaluation.splits import (
    SplitFile,
    budget_sample,
    carve_banks,
    prepare_dataset,
    read_split_file,
    snapshot_hash,
    split_by_question,
    write_split_file,
)


def _items(nq=20, per_q=lambda q: 3 + q % 7):
    return [EvalItem(f"i{q}-{k}", "engsaf", f"q{q}", "Q", f"a{k}", "en", k % 3, 3, "")
            for q in range(nq) for k in range(per_q(q))]


class SplitsTest(unittest.TestCase):
    def test_no_question_in_both_splits(self):
        out = split_by_question(_items())
        dev = {i.question_id for i in out if i.split == "dev"}
        test = {i.question_id for i in out if i.split == "test"}
        self.assertFalse(dev & test)
        share = sum(i.split == "dev" for i in out) / len(out)
        self.assertTrue(0.4 <= share < 0.6)

    def test_split_is_deterministic(self):
        self.assertEqual(split_by_question(_items()), split_by_question(_items()))

    def test_bank_size_rule(self):
        out = carve_banks(_items(nq=3, per_q=lambda q: [2, 12, 40][q]))
        banks = Counter(i.question_id for i in out if i.role == "bank")
        self.assertEqual({"q1": 4, "q2": 9}, dict(banks))

    def test_budget_sample_preserves_questions_and_banks(self):
        items = carve_banks(split_by_question(_items(nq=40, per_q=lambda q: 30)))
        out = budget_sample(items, "test", cap=100)
        kept = [i for i in out if i.split == "test" and i.role == "eval"]
        self.assertTrue(90 <= len(kept) <= 110)
        self.assertEqual({i.question_id for i in items if i.split == "test"},
                         {i.question_id for i in kept})
        self.assertEqual(sum(i.role == "bank" for i in items), sum(i.role == "bank" for i in out))

    def test_budget_sample_under_cap_unchanged(self):
        items = carve_banks(split_by_question(_items()))
        self.assertEqual(items, budget_sample(items, "test", cap=10000))

    def test_budget_sample_deterministic(self):
        items = carve_banks(split_by_question(_items(nq=40, per_q=lambda q: 30)))
        self.assertEqual(budget_sample(items, "dev", 50), budget_sample(items, "dev", 50))

    def test_private_split_file_hashes_ids(self):
        _, sf = prepare_dataset("engsaf", _items())
        with tempfile.TemporaryDirectory() as d:
            write_split_file(Path(d) / "s.json", sf, hash_ids=True)
            text = (Path(d) / "s.json").read_text()
            back = read_split_file(Path(d) / "s.json")
        self.assertNotIn('"i0-0"', text)
        self.assertIn('"hashed": true', text)
        self.assertEqual(sf.snapshot, back.snapshot)
        self.assertEqual(len(sf.splits["dev"]), len(back.splits["dev"]))

    def test_public_split_file_roundtrip(self):
        _, sf = prepare_dataset("engsaf", _items())
        with tempfile.TemporaryDirectory() as d:
            write_split_file(Path(d) / "s.json", sf, hash_ids=False)
            self.assertEqual(sf, read_split_file(Path(d) / "s.json"))

    def test_prepare_engsaf_counts_and_snapshot(self):
        items, sf = prepare_dataset("engsaf", _items())
        self.assertEqual(sf.snapshot, snapshot_hash(items))
        self.assertEqual(sf.counts["dev"], len(sf.splits["dev"]))
        self.assertEqual(sf.counts["test_bank"], len(sf.banks["test"]))
        self.assertEqual(sf.splits["dev"], sorted(sf.splits["dev"]))

    def test_prepare_scientsbank_banks_every_split(self):
        items = [EvalItem(f"s{s}-{q}-{k}", "scientsbank", f"{s}-q{q}", "Q", "a", "en",
                          k % 2, 2, s)
                 for s in ("dev", "test_ua", "test_uq") for q in range(3) for k in range(12)]
        out, sf = prepare_dataset("scientsbank", items)
        self.assertEqual(len(out), len(items))
        for s in ("dev", "test_ua", "test_uq"):
            self.assertEqual(len(sf.banks[s]), 3 * 4)

    def test_prepare_case_and_synthetic_no_banks(self):
        for name, split in (("jk_case", "case"), ("synthetic", "smoke")):
            items = [EvalItem(f"c{k}", name, "q", "Q", "a", "id", 1, 3, split)
                     for k in range(30)]
            out, sf = prepare_dataset(name, items)
            self.assertEqual(items, out)
            self.assertEqual(sf.banks.get(split, []), [])

    def test_snapshot_hash_order_independent(self):
        items = _items()
        self.assertEqual(snapshot_hash(items), snapshot_hash(list(reversed(items))))

    def test_bank_and_sample_use_separate_seed_namespaces(self):
        items = split_by_question(_items(nq=10, per_q=lambda q: 30))
        banked = carve_banks(items, seed=7)
        for q in {i.question_id for i in items}:
            for split in ("dev", "test"):
                group = sorted((i for i in items if i.question_id == q and i.split == split),
                               key=lambda i: i.item_id)
                if not group:
                    continue
                random.Random(f"7:bank:{split}:{q}").shuffle(group)
                expect = {i.item_id for i in group[:min(9, len(group) // 3)]}
                got = {i.item_id for i in banked if i.question_id == q and i.role == "bank"}
                self.assertEqual(expect, got)
        sampled = budget_sample(banked, "test", cap=50, seed=7)
        total = sum(1 for i in banked if i.split == "test" and i.role == "eval")
        for q in {i.question_id for i in banked if i.split == "test"}:
            group = sorted((i for i in banked if i.question_id == q and i.split == "test"
                            and i.role == "eval"), key=lambda i: i.item_id)
            keep = min(len(group), max(1, round(len(group) * 50 / total)))
            random.Random(f"7:sample:test:{q}").shuffle(group)
            expect = {i.item_id for i in group[:keep]}
            got = {i.item_id for i in sampled if i.question_id == q and i.split == "test"
                   and i.role == "eval"}
            self.assertEqual(expect, got)

    def test_duplicate_item_ids_rejected_without_text(self):
        items = _items()
        dup = items + [items[0], items[1]]
        for name in ("engsaf", "jk_case", "synthetic"):
            with self.assertRaises(ValueError) as ctx:
                prepare_dataset(name, dup)
            self.assertIn("2 duplicate item_ids", str(ctx.exception))
            self.assertNotIn("i0-0", str(ctx.exception))

    def test_banks_disjoint_from_eval_and_hashed_file_has_no_raw_ids(self):
        out, sf = prepare_dataset("engsaf", _items(nq=40, per_q=lambda q: 30))
        for split in sf.splits:
            self.assertFalse(set(sf.splits[split]) & set(sf.banks.get(split, [])))
        all_eval = {i for v in sf.splits.values() for i in v}
        all_bank = {i for v in sf.banks.values() for i in v}
        self.assertFalse(all_eval & all_bank)
        self.assertEqual(len(out), len(all_eval) + len(all_bank))
        with tempfile.TemporaryDirectory() as d:
            write_split_file(Path(d) / "s.json", sf, hash_ids=True)
            text = (Path(d) / "s.json").read_text()
        for item in out:
            self.assertNotIn(item.item_id, text)
            self.assertNotIn(item.question_id, text)


if __name__ == "__main__":
    unittest.main()
