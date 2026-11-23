import dataclasses
import json
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from src.evaluation import paths, report
from src.evaluation.experiment import ExperimentConfig
from src.evaluation.graders.stub import StubGrader
from src.evaluation.privacy import PrivacyError, assert_output_allowed
from src.evaluation.report import (
    build_manifest,
    fit_run_thresholds,
    load_run,
    render_json,
    render_markdown,
    write_report,
)
from src.evaluation.runner import plan_run, run
from src.evaluation.schema import EvalItem
from src.evaluation.splits import SplitFile, snapshot_hash

CANARY_Q, CANARY_A, CANARY_R = "CANARY-Q-7f3a", "CANARY-A-91bc", "CANARY-R-55de"
CANARY_ID, CANARY_QID = "CANARY-ID-3c1e", "CANARY-QID-8d24"
CANARY_FB, CANARY_SRC = "CANARY-FB-6b07", "CANARY-SRC-e4a9"
CANARIES = (CANARY_Q, CANARY_A, CANARY_R, CANARY_ID, CANARY_QID, CANARY_FB, CANARY_SRC)


def _canary_items():
    items = []
    for i in range(40):
        q = i % 4
        # Question 3 uses a document reference, so its gold_source is the canary file name.
        doc = q == 3
        items.append(EvalItem(
            f"{CANARY_ID}-e{i}", "engsaf", f"{CANARY_QID}-q{q}", f"{CANARY_Q} question {q}",
            f"{CANARY_A} word{i % 3}", "en", i % 3, 3, "dev" if i < 20 else "test",
            reference_text=None if doc else f"{CANARY_R} word{q}",
            reference_document=f"/nonexistent/{CANARY_SRC}.pdf" if doc else None))
    return items


class CanaryGrader(StubGrader):
    """StubGrader whose per-item output carries canaries in feedback and sources."""

    def grade(self, namespace, item, request):
        raw = super().grade(namespace, item, request)
        return dataclasses.replace(
            raw, feedback=f"{CANARY_FB} echoing {request.answer}",
            retrieved_sources=list(raw.retrieved_sources) + [f"{CANARY_SRC}-retrieved.txt"])


def _cfg():
    return ExperimentConfig(
        name="canary", phase="4a", grader="stub", model=None, provider="stub",
        context_mode="rag", temperature=None, datasets={"engsaf": ["dev", "test"]},
        repeats=1, variant_set=None, price_in_per_mtok=0.0, price_out_per_mtok=0.0,
        concurrency=2, max_cost_usd=0.0, overrides={},
    )


def _canaries_in(text):
    return [c for c in CANARIES if c in text]


class GuardTests(unittest.TestCase):
    def test_private_run_refuses_public_out_dir(self):
        with self.assertRaises(PrivacyError):
            assert_output_allowed(["engsaf"], paths.REPORTS_DIR)

    def test_private_run_refuses_temp_dir(self):
        with self.assertRaises(PrivacyError):
            assert_output_allowed(["scientsbank", "jk_case"], Path(tempfile.gettempdir()))

    def test_public_dataset_may_write_anywhere(self):
        assert_output_allowed(["scientsbank", "synthetic"], Path(tempfile.gettempdir()))

    def test_private_dataset_allowed_under_private_dir(self):
        assert_output_allowed(["engsaf"], paths.PRIVATE_DIR / "evaluation" / "x")

    def test_report_module_reexports_guard(self):
        self.assertIs(report.assert_output_allowed, assert_output_allowed)
        self.assertIs(report.PrivacyError, PrivacyError)


class CanaryTests(unittest.TestCase):
    def setUp(self):
        self.out_root = paths.PRIVATE_DIR / "evaluation" / f"_canary_test_{uuid.uuid4().hex}"
        self.tmp = Path(tempfile.mkdtemp())
        self.items = _canary_items()
        self.cfg = _cfg()
        plan = plan_run(self.cfg, {"engsaf": self.items}, self.out_root)
        run(plan, CanaryGrader(), sleep=lambda s: None)
        self.plan = plan
        self.run_dir = plan.out_dir

    def tearDown(self):
        shutil.rmtree(self.out_root, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _report(self, report_dir: Path, aggregate_fn=report.aggregate):
        """The full report path: load, fit, aggregate, manifest, render and write."""
        results, summary = load_run(self.run_dir)
        ths = fit_run_thresholds(results, self.cfg.datasets)
        agg = aggregate_fn(results, self.cfg, ths, n_resamples=50)
        split = SplitFile("engsaf", snapshot_hash(self.items), 20261123,
                          {"dev": [i.item_id for i in self.items[:20]],
                           "test": [i.item_id for i in self.items[20:]]},
                          {"dev": [], "test": []}, {"dev": 20, "test": 20})
        manifest = build_manifest(self.cfg, self.plan.config_hash, summary,
                                  {"engsaf": split}, {"engsaf": snapshot_hash(self.items)},
                                  embedding_model="BAAI/bge-m3", thresholds=ths,
                                  results=results)
        written = write_report(agg, manifest, report_dir / "2026-11-23-4a-canary")
        texts = [render_markdown(agg, manifest), json.dumps(render_json(agg, manifest))]
        files = [f for f in report_dir.rglob("*") if f.is_file()]
        texts += [f.read_text(encoding="utf-8") for f in files]
        return written, files, texts

    def test_per_item_output_carries_canaries(self):
        # Non-vacuous precondition: the per-item results really hold leakable canaries.
        text = (self.run_dir / "results.jsonl").read_text(encoding="utf-8")
        for c in (CANARY_A, CANARY_FB, CANARY_ID, CANARY_QID, CANARY_SRC):
            self.assertIn(c, text)
        results, _ = load_run(self.run_dir)
        self.assertTrue(any(CANARY_SRC in r.gold_source for r in results))
        self.assertTrue(all(any(CANARY_SRC in s for s in r.retrieved_sources)
                            for r in results))

    def test_no_canary_in_any_report_output(self):
        report_dir = self.tmp / "reports"
        written, files, texts = self._report(report_dir)
        self.assertEqual(2, len(written))
        self.assertEqual({".md", ".json"}, {f.suffix for f in files})
        for text in texts:
            self.assertEqual([], _canaries_in(text))

    def test_scan_detects_a_leak(self):
        # Regression self-check: a leaky aggregate must make the canary scan fail.
        def leaky(results, cfg, ths, **kw):
            agg = report.aggregate(results, cfg, ths, **kw)
            agg.extra["leak"] = [r.feedback for r in results]
            return agg

        _, _, texts = self._report(self.tmp / "leaky", aggregate_fn=leaky)
        leaked = {c for t in texts for c in _canaries_in(t)}
        self.assertIn(CANARY_FB, leaked)
        self.assertIn(CANARY_A, leaked)

    def test_per_item_files_only_under_private_data(self):
        report_dir = self.tmp / "reports"
        self._report(report_dir)
        self.assertEqual([], list(report_dir.rglob("*.jsonl")))
        bearing = []
        for root in (report_dir, self.out_root):
            for f in root.rglob("*"):
                if f.is_file() and _canaries_in(f.read_text(encoding="utf-8",
                                                            errors="ignore")):
                    bearing.append(f)
        self.assertTrue(bearing)
        self.assertIn(self.run_dir / "results.jsonl", bearing)
        for f in bearing:
            self.assertTrue(paths.is_private_path(f), f"canary outside private-data: {f}")


if __name__ == "__main__":
    unittest.main()
