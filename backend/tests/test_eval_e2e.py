"""CLI end-to-end: prepare -> run -> report -> report --thresholds-from -> compare.

Offline, stub grader, invented data only. Every private source string carries a canary;
the test asserts that the canary never reaches stdout, stderr, a report or a public file.
Private paths are redirected to a throwaway ``private-data/evaluation/_e2e_test_<uuid>``.
"""

import contextlib
import csv
import io
import json
import random
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from src.evaluation import __main__ as cli
from src.evaluation import paths
from src.evaluation.datasets.scientsbank import rows_to_items

CANARY = "QZXCANARYQZX"
LABELS = ["correct", "contradictory", "partially_correct_incomplete", "irrelevant",
          "non_domain"]


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch("sys.stdin", io.StringIO("")):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _write_engsaf(path: Path, rng: random.Random) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Question_id", "Question", "Student Answer", "Correct Answer",
                    "output_label", "feedback"])
        for q in range(24):
            for a in range(rng.randint(6, 14)):
                g = rng.choice([0, 1, 2])
                answer = (f"{CANARY} answer {q} {a} " + " ".join(["word"] * g * 3)
                          + f" ref{q}" * g)
                w.writerow([q, f"Invented question {q} {CANARY}?", answer,
                            f"ref{q} reference words {CANARY}", g, f"{CANARY} feedback"])


def _write_case(directory: Path, rng: random.Random) -> None:
    with open(directory / "case.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["soal", "jawaban", "nilai"])
        for q in range(4):
            for s in range(8):
                w.writerow([f"Soal karangan {q} {CANARY}",
                            f"jawaban {CANARY} {q} {s} kata kata kata kata", rng.randint(0, 25)])
    (directory / "key.pdf").write_bytes(f"%PDF-1.4 invented {CANARY}".encode())


def _scientsbank_items(rng: random.Random):
    items = []
    for split, nq, offset in (("train", 12, 0), ("test_ua", 12, 0), ("test_uq", 6, 100)):
        rows = [{"id": f"{split}{q}-{a}", "question": f"science question {q + offset}",
                 "student_answer": f"public answer {a} ref{q + offset}" * (a % 3 + 1),
                 "reference_answer": f"ref{q + offset} good", "label": rng.randrange(5)}
                for q in range(nq) for a in range(10)]
        items += rows_to_items(rows, split)
    return items


class CliEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.root = paths.PRIVATE_DIR / "evaluation" / f"_e2e_test_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.public = self.tmp / "public_splits"
        for name, value in {
            "PREPARED_DIR": self.root / "prepared",
            "PRIVATE_SPLITS_DIR": self.root / "splits",
            "PUBLIC_SPLITS_DIR": self.public,
            "CHECKSUMS_FILE": self.public / "private_checksums.json",
            "DEFAULT_RUNS_ROOT": self.root / "runs",
            "REPORTS_DIR": self.tmp / "docs",
        }.items():
            p = mock.patch.object(cli, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.texts = []

    def call(self, argv):
        code, out, err = _run(argv)
        self.texts.append(out + err)
        self.assertEqual(0, code, f"{argv[0]} failed: {err}")
        return out

    def config(self, name, datasets, extra=""):
        path = self.tmp / f"{name}.yaml"
        path.write_text(f"name: {name}\nphase: \"4a\"\ngrader: stub\nprovider: stub\n"
                        f"datasets:\n{datasets}concurrency: 2\nmax_cost_usd: 0.0\n"
                        f"overrides: {{}}\n{extra}", encoding="utf-8")
        return path

    def run_dir(self, out):
        return [line.split("results: ", 1)[1] for line in out.splitlines()
                if line.startswith("results: ")][0]

    def test_prepare_run_report_compare_without_leaks(self):
        rng = random.Random(5)
        src = self.tmp / "sources"
        src.mkdir()
        _write_engsaf(src / "engsaf.csv", rng)
        _write_case(src, rng)
        sci = _scientsbank_items(rng)
        original = cli._load_source

        def load(name, source, pdf):
            return (sci, {"items": len(sci)}) if name == "scientsbank" else \
                original(name, source, pdf)

        with mock.patch.object(cli, "_load_source", side_effect=load):
            self.call(["prepare", "--dataset", "engsaf", "--source", str(src / "engsaf.csv")])
            self.call(["prepare", "--dataset", "scientsbank"])
            self.call(["prepare", "--dataset", "jk_case", "--source", str(src / "case.csv"),
                       "--reference-pdf", str(src / "key.pdf")])

        all_sets = ("  engsaf: [dev, test]\n  scientsbank: [dev, test_uq, test_ua]\n"
                    "  jk_case: [case]\n")
        base = self.run_dir(self.call(["run", "--experiment",
                                       str(self.config("e2e-base", all_sets)), "--yes"]))
        limited = self.run_dir(self.call([
            "run", "--experiment",
            str(self.config("e2e-limited", all_sets, "max_items_per_split: 5\n")), "--yes"]))
        inj = self.run_dir(self.call([
            "run", "--experiment",
            str(self.config("e2e-injection", "  engsaf: [dev, test]\n  scientsbank: [dev]\n",
                            "variant_set: injection\n")), "--yes"]))

        docs = self.tmp / "docs"
        self.call(["report", "--run-dir", base, "--out", str(docs / "base")])
        self.call(["report", "--run-dir", inj, "--out", str(docs / "inj"),
                   "--thresholds-from", str(docs / "base.json")])
        out = self.call(["compare", "--run-dir", base, "--run-dir", limited,
                         "--out", str(docs / "cmp.md")])

        base_json = json.loads((docs / "base.json").read_text(encoding="utf-8"))
        self.assertEqual({"engsaf", "jk_case", "scientsbank"}, set(base_json["metrics"]))
        self.assertEqual({"grader": "stub"}, base_json["manifest"]["effective_settings"])
        inj_md = (docs / "inj.md").read_text(encoding="utf-8")
        self.assertIn("### Injection", inj_md)
        self.assertIn("Frozen thresholds loaded from", inj_md)
        self.assertIn("case study: descriptive only", out)
        self.assertIn("A failures", out)
        self.assertTrue(list(self.public.glob("*.json")))

        blobs = list(self.texts)
        blobs += [p.read_text(encoding="utf-8") for p in sorted(docs.iterdir())]
        blobs += [p.read_text(encoding="utf-8") for p in sorted(self.public.iterdir())]
        for blob in blobs:
            self.assertNotIn(CANARY, blob)
        # The canary is really in the prepared private items (the check is not vacuous).
        prepared = (self.root / "prepared" / "engsaf.jsonl").read_text(encoding="utf-8")
        self.assertIn(CANARY, prepared)


if __name__ == "__main__":
    unittest.main()
