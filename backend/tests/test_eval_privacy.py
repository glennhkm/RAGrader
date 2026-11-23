import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from src.evaluation import paths
from src.evaluation.experiment import ExperimentConfig
from src.evaluation.graders.stub import StubGrader
from src.evaluation.privacy import PrivacyError, assert_output_allowed
from src.evaluation.report import (
    aggregate,
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
CANARIES = (CANARY_Q, CANARY_A, CANARY_R)


def _canary_items():
    return [EvalItem(f"e{i}", "engsaf", f"q{i % 4}", f"{CANARY_Q} question {i % 4}",
                     f"{CANARY_A} word{i % 3}", "en", i % 3, 3,
                     "dev" if i < 20 else "test",
                     reference_text=f"{CANARY_R} word{i % 4}")
            for i in range(40)]


def _cfg():
    return ExperimentConfig(
        name="canary", phase="4a", grader="stub", model=None, provider="stub",
        context_mode="rag", temperature=None, datasets={"engsaf": ["dev", "test"]},
        repeats=1, variant_set=None, price_in_per_mtok=0.0, price_out_per_mtok=0.0,
        concurrency=2, max_cost_usd=0.0, overrides={},
    )


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
        from src.evaluation import report
        self.assertIs(report.assert_output_allowed, assert_output_allowed)
        self.assertIs(report.PrivacyError, PrivacyError)


class CanaryTests(unittest.TestCase):
    def setUp(self):
        self.out_root = paths.PRIVATE_DIR / "evaluation" / f"_canary_test_{uuid.uuid4().hex}"
        self.report_dir = Path(tempfile.mkdtemp())
        items = _canary_items()
        cfg = _cfg()
        plan = plan_run(cfg, {"engsaf": items}, self.out_root)
        run(plan, StubGrader(), sleep=lambda s: None)
        results, summary = load_run(plan.out_dir)
        ths = fit_run_thresholds(results, cfg.datasets)
        agg = aggregate(results, cfg, ths, n_resamples=50)
        split = SplitFile("engsaf", snapshot_hash(items), 20261123,
                          {"dev": [i.item_id for i in items[:20]],
                           "test": [i.item_id for i in items[20:]]},
                          {"dev": [], "test": []}, {"dev": 20, "test": 20})
        manifest = build_manifest(cfg, plan.config_hash, summary, {"engsaf": split},
                                  {"engsaf": snapshot_hash(items)},
                                  embedding_model="BAAI/bge-m3", thresholds=ths,
                                  results=results)
        self.md = render_markdown(agg, manifest)
        self.js = render_json(agg, manifest)
        self.written = write_report(agg, manifest, self.report_dir / "2026-11-23-4a-canary")
        self.run_dir = plan.out_dir

    def tearDown(self):
        shutil.rmtree(self.out_root, ignore_errors=True)
        shutil.rmtree(self.report_dir, ignore_errors=True)

    def test_no_canary_in_any_report_output(self):
        import json
        self.assertEqual(2, len(self.written))
        texts = [self.md, json.dumps(self.js)]
        texts += [f.read_text(encoding="utf-8") for f in self.report_dir.rglob("*")
                  if f.is_file()]
        self.assertTrue(all(f.suffix in (".md", ".json") for f in self.report_dir.rglob("*")
                            if f.is_file()))
        for text in texts:
            for c in CANARIES:
                self.assertNotIn(c, text)
        self.assertIn("thresholds", self.js)

    def test_per_item_files_only_under_private_data(self):
        self.assertTrue((self.run_dir / "results.jsonl").exists())
        self.assertTrue(paths.is_private_path(self.run_dir))
        for root in (self.report_dir, self.out_root):
            for f in root.rglob("*"):
                if not f.is_file():
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")
                if any(c in text for c in CANARIES):
                    self.assertTrue(paths.is_private_path(f),
                                    f"canary outside private-data: {f}")


if __name__ == "__main__":
    unittest.main()
