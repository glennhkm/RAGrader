import dataclasses
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from loguru import logger

from src.evaluation.experiment import ExperimentConfig
from src.evaluation.graders.base import RawGrade, TransientGraderError
from src.evaluation.graders.http import http_namespace
from src.evaluation.graders.stub import StubGrader
from src.evaluation import paths
from src.evaluation.privacy import PrivacyError
from src.evaluation.materials import gold_source
from src.evaluation.runner import (
    BudgetError,
    RunSummary,
    plan_run,
    read_summary,
    run,
)
from src.evaluation.schema import EvalItem, EvalResult, append_jsonl, read_results


def _cfg(**kw):
    base = dict(
        name="t", phase="4a", grader="stub", model=None, provider="stub",
        context_mode="rag", temperature=None, datasets={"synthetic": ["smoke"]},
        repeats=1, variant_set=None, price_in_per_mtok=0.0, price_out_per_mtok=0.0,
        concurrency=2, max_cost_usd=0.0, overrides={},
    )
    base.update(kw)
    return ExperimentConfig(**base)


def _items(n, dataset="synthetic", split="smoke", lang="en"):
    return [EvalItem(f"{dataset}-{k:03d}", dataset, f"q{k % 3}", "Q?", f"answer {k}", lang,
                     k % 3, 3, split, reference_text=f"reference {k % 3}",
                     gold_score=float(k), gold_label_raw=str(k % 3))
            for k in range(n)]


def _ok(prompt_tokens=2000, completion_tokens=300):
    return RawGrade(
        success=True, score=50.0, confidence=0.8, feedback="fine", error_type=None,
        integrity_warnings=["w1"], citations_kept=1, citations_dropped=0,
        retrieved_sources=["s1", "s2"], provider="fake", prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens, tokens_estimated=False)


class Interrupt(BaseException):
    pass


class FakeGrader:
    name = "fake"

    def __init__(self, fail_after=None, prompt_tokens=2000):
        self.prepared = {}
        self.calls = 0
        self.fail_after = fail_after
        self.prompt_tokens = prompt_tokens
        self._lock = threading.Lock()

    def prepare_namespace(self, namespace, docs, workdir):
        self.prepared[namespace] = (list(docs), Path(workdir))

    def grade(self, namespace, item, request):
        with self._lock:
            self.calls += 1
            n = self.calls
        if self.fail_after is not None and n > self.fail_after:
            raise Interrupt()
        return _ok(prompt_tokens=self.prompt_tokens)

    def close(self):
        pass


class AlwaysTransient(FakeGrader):
    def __init__(self, retry_after=None):
        super().__init__()
        self.retry_after = retry_after

    def grade(self, namespace, item, request):
        self.calls += 1
        raise TransientGraderError("429", retry_after=self.retry_after)


class ExplodingGrader(FakeGrader):
    def prepare_namespace(self, namespace, docs, workdir):
        raise AssertionError("prepare_namespace must not be called")

    def grade(self, namespace, item, request):
        raise AssertionError("grade must not be called")


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def _plan(self, n=10, **kw):
        return plan_run(_cfg(**kw), {"synthetic": _items(n)}, self.root)

    def test_plan_out_dir_and_estimate(self):
        plan = self._plan(n=10, price_in_per_mtok=1.0, price_out_per_mtok=2.0,
                          max_cost_usd=1.0)
        self.assertEqual(self.root / f"t-{plan.config_hash}", plan.out_dir)
        self.assertEqual(16, len(plan.config_hash))
        self.assertAlmostEqual(10 * (2000 * 1.0 + 300 * 2.0) / 1e6, plan.estimated_cost_usd)

    def test_plan_selects_eval_role_of_configured_splits(self):
        items = _items(4) + [dataclasses.replace(_items(1)[0], item_id="bank", role="bank")]
        items += _items(2, dataset="scientsbank", split="test_ua")
        sci_dev = _items(3, dataset="scientsbank", split="dev")
        plan = plan_run(_cfg(datasets={"synthetic": ["smoke"], "scientsbank": ["dev"]}),
                        {"synthetic": items[:5], "scientsbank": items[5:] + sci_dev},
                        self.root)
        self.assertEqual(sorted([i.item_id for i in _items(4)] + [i.item_id for i in sci_dev]),
                         sorted(i.item_id for i in plan.items))

    def test_max_items_per_split_takes_first_n_by_item_id(self):
        sci = _items(7, dataset="scientsbank", split="test_uq")
        sci += _items(5, dataset="scientsbank", split="dev")
        sci = list(reversed(sci))  # input order must not matter
        plan = plan_run(_cfg(datasets={"synthetic": ["smoke"], "scientsbank": ["dev", "test_uq"]},
                             max_items_per_split=3),
                        {"synthetic": list(reversed(_items(10))), "scientsbank": sci}, self.root)
        per = {}
        for i in plan.items:
            per.setdefault((i.dataset, i.split), []).append(i.item_id)
        self.assertEqual(["synthetic-000", "synthetic-001", "synthetic-002"],
                         per[("synthetic", "smoke")])
        self.assertEqual(["scientsbank-000", "scientsbank-001", "scientsbank-002"],
                         per[("scientsbank", "dev")])
        self.assertEqual(3, len(per[("scientsbank", "test_uq")]))
        self.assertEqual(9, len(plan.items))
        unlimited = plan_run(_cfg(), {"synthetic": _items(10)}, self.root)
        self.assertEqual(10, len(unlimited.items))

    def test_stub_grader_end_to_end(self):
        plan = self._plan(n=5)
        s = run(plan, StubGrader(), sleep=lambda s: None)
        self.assertEqual((5, 0, None, {}), (s.graded, s.skipped_existing, s.aborted, s.failures))
        self.assertEqual((5 * 2000, 5 * 300), (s.tokens_in, s.tokens_out))
        results = read_results(plan.out_dir / "results.jsonl")
        self.assertEqual(5, len(results))
        self.assertTrue(all(r.success and r.config_hash == plan.config_hash for r in results))
        self.assertTrue((plan.out_dir / "work").is_dir())

    def test_result_fields_carried_from_item_and_grade(self):
        plan = self._plan(n=1)
        ticks = iter([10.0, 12.5])
        run(plan, FakeGrader(), clock=lambda: next(ticks), sleep=lambda s: None)
        (r,) = read_results(plan.out_dir / "results.jsonl")
        item = plan.items[0]
        self.assertEqual(EvalResult(
            item_id=item.item_id, config_hash=plan.config_hash, dataset="synthetic",
            question_id=item.question_id, split="smoke", gold_label=item.gold_label,
            success=True, score=50.0, confidence=0.8, error_type=None,
            integrity_warnings=("w1",), citations_kept=1, citations_dropped=0,
            retrieved_sources=("s1", "s2"), gold_source=gold_source(item), provider="fake",
            prompt_tokens=2000, completion_tokens=300, tokens_estimated=False, latency_s=2.5,
            repeat=0, variant=None, derived_from=None, gold_score=item.gold_score,
            gold_label_raw=item.gold_label_raw, feedback="fine"), r)

    def test_namespace_per_dataset_with_all_items_and_one_workdir(self):
        syn = _items(4) + [dataclasses.replace(_items(4)[0], item_id="b", question_id="qb",
                                               role="bank")]
        sci = _items(2, dataset="scientsbank", split="dev")
        sci += [dataclasses.replace(sci[0], item_id="ua", question_id="qua", split="test_ua")]
        plan = plan_run(_cfg(datasets={"synthetic": ["smoke"], "scientsbank": ["dev"]}),
                        {"synthetic": syn, "scientsbank": sci}, self.root)
        g = FakeGrader()
        run(plan, g, sleep=lambda s: None)
        ns_syn = http_namespace(plan.config_hash, "synthetic")
        ns_sci = http_namespace(plan.config_hash, "scientsbank")
        self.assertEqual({ns_syn, ns_sci}, set(g.prepared))
        self.assertEqual(4, len(g.prepared[ns_syn][0]))   # q0, q1, q2 and the bank's qb
        self.assertEqual(3, len(g.prepared[ns_sci][0]))   # q0, q1 and test_ua's qua
        self.assertEqual({plan.out_dir / "work"}, {w for _, w in g.prepared.values()})

    def test_resume_skips_completed_items(self):
        plan = self._plan(n=10, concurrency=1)
        with self.assertRaises(Interrupt):
            run(plan, FakeGrader(fail_after=4), sleep=lambda s: None)
        self.assertEqual(4, len(read_results(plan.out_dir / "results.jsonl")))
        s2 = run(plan, FakeGrader(), sleep=lambda s: None)
        self.assertEqual((6, 4), (s2.graded, s2.skipped_existing))
        results = read_results(plan.out_dir / "results.jsonl")
        self.assertEqual(10, len(results))
        self.assertEqual(10, len({r.item_id for r in results}))

    def test_resume_from_prewritten_results(self):
        plan = self._plan(n=10)
        path = plan.out_dir / "results.jsonl"
        for item in plan.items[:4]:
            append_jsonl(path, EvalResult(item.item_id, plan.config_hash, item.dataset,
                                          item.question_id, item.split, item.gold_label,
                                          True, 1.0, 1.0))
        g = FakeGrader()
        s = run(plan, g, sleep=lambda s: None)
        self.assertEqual((6, 4, 6), (s.graded, s.skipped_existing, g.calls))

    def test_partial_trailing_line_truncated_before_append(self):
        plan = self._plan(n=3)
        path = plan.out_dir / "results.jsonl"
        item = plan.items[0]
        append_jsonl(path, EvalResult(item.item_id, plan.config_hash, item.dataset,
                                      item.question_id, item.split, item.gold_label,
                                      True, 1.0, 1.0))
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"item_id": "synthetic-001", "config_ha')
        s = run(plan, FakeGrader(), sleep=lambda s: None)
        self.assertEqual((2, 1), (s.graded, s.skipped_existing))
        lines = path.read_text(encoding="utf-8").split("\n")
        self.assertEqual("", lines[-1])
        self.assertEqual(3, len(lines) - 1)
        for line in lines[:-1]:
            json.loads(line)   # every line is a complete record
        self.assertEqual(sorted(i.item_id for i in plan.items),
                         sorted(r.item_id for r in read_results(path)))

    def test_other_config_hash_refused(self):
        plan = self._plan(n=2)
        item = plan.items[0]
        append_jsonl(plan.out_dir / "results.jsonl",
                     EvalResult(item.item_id, "0" * 16, item.dataset, item.question_id,
                                item.split, item.gold_label, True, 1.0, 1.0))
        with self.assertRaisesRegex(ValueError, "results.jsonl belongs to another configuration"):
            run(plan, ExplodingGrader(), sleep=lambda s: None)

    def test_other_config_hash_refused_without_touching_file(self):
        plan = self._plan(n=2)
        path = plan.out_dir / "results.jsonl"
        item = plan.items[0]
        append_jsonl(path, EvalResult(item.item_id, "0" * 16, item.dataset, item.question_id,
                                      item.split, item.gold_label, True, 1.0, 1.0))
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"item_id": "synthetic-001", "config_ha')
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "results.jsonl belongs to another configuration"):
            run(plan, ExplodingGrader(), sleep=lambda s: None)
        self.assertEqual(before, path.read_bytes())

    def test_budget_cap_is_cumulative_across_resume(self):
        plan = self._plan(n=10, price_in_per_mtok=1.0, max_cost_usd=0.03, concurrency=1)
        s1 = run(plan, FakeGrader(prompt_tokens=20000), sleep=lambda s: None)
        self.assertEqual(("budget", 2), (s1.aborted, s1.graded))
        g = ExplodingGrader()
        s2 = run(plan, g, sleep=lambda s: None)
        self.assertEqual(("budget", 0, 2), (s2.aborted, s2.graded, s2.skipped_existing))
        self.assertAlmostEqual(0.04, s2.cost_usd)
        self.assertEqual(0.0, s2.cost_usd_this_run)
        self.assertEqual(40000, s2.tokens_in)
        self.assertEqual(2, len(read_results(plan.out_dir / "results.jsonl")))

    def test_resume_cost_includes_prior_records(self):
        plan = self._plan(n=4, price_in_per_mtok=1.0, max_cost_usd=0.05, concurrency=1)
        # each call costs 0.02 actual; two runs together must stop at the same cap
        s1 = run(dataclasses.replace(plan, items=plan.items[:1]),
                 FakeGrader(prompt_tokens=20000), sleep=lambda s: None)
        self.assertEqual((None, 1), (s1.aborted, s1.graded))
        s2 = run(plan, FakeGrader(prompt_tokens=20000), sleep=lambda s: None)
        self.assertEqual(("budget", 2, 1), (s2.aborted, s2.graded, s2.skipped_existing))
        self.assertAlmostEqual(0.06, s2.cost_usd)
        self.assertAlmostEqual(0.04, s2.cost_usd_this_run)

    def test_retry_after_capped_at_60(self):
        slept = []
        run(self._plan(n=1), AlwaysTransient(retry_after=120.0), sleep=slept.append,
            max_attempts=2)
        self.assertEqual([60], slept)

    def test_stop_flag_checked_before_retry(self):
        plan = self._plan(n=2, price_in_per_mtok=1.0, max_cost_usd=0.03, concurrency=2)
        path = plan.out_dir / "results.jsonl"

        class Mixed(FakeGrader):
            def grade(self, namespace, item, request):
                with self._lock:
                    self.calls += 1
                if item.item_id.endswith("000"):
                    raise TransientGraderError("429", retry_after=1.0)
                return _ok(prompt_tokens=40000)   # 0.04 > 0.03: trips the cap

        def wait_for_record(_):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if path.exists() and path.read_text(encoding="utf-8").count("\n") >= 1:
                    return
                time.sleep(0.01)

        g = Mixed()
        s = run(plan, g, sleep=wait_for_record, max_attempts=5)
        self.assertEqual(("budget", 1, 2), (s.aborted, s.graded, g.calls))
        self.assertEqual(["synthetic-001"], [r.item_id for r in read_results(path)])

    def test_backoff_honours_retry_after_then_gives_up(self):
        slept = []
        plan = self._plan(n=1)
        g = AlwaysTransient(retry_after=2.0)
        run(plan, g, sleep=slept.append, max_attempts=3)
        self.assertEqual([2.0, 2.0], slept)
        self.assertEqual(3, g.calls)
        summary = read_summary(plan.out_dir / "run_summary.json")
        self.assertEqual({"provider_error": 1}, summary.failures)
        (r,) = read_results(plan.out_dir / "results.jsonl")
        self.assertEqual((False, "provider_error", None), (r.success, r.error_type, r.score))

    def test_backoff_exponential_without_retry_after(self):
        slept = []
        run(self._plan(n=1), AlwaysTransient(), sleep=slept.append, max_attempts=8)
        self.assertEqual([2, 4, 8, 16, 32, 60, 60], slept)

    def test_unsuccessful_grade_recorded_as_failure(self):
        class ParseFail(FakeGrader):
            def grade(self, namespace, item, request):
                raw = _ok()
                raw.success, raw.score, raw.error_type = False, None, "parse_failure"
                return raw

        plan = self._plan(n=3)
        s = run(plan, ParseFail(), sleep=lambda s: None)
        self.assertEqual((3, {"parse_failure": 3}), (s.graded, s.failures))
        self.assertTrue(all(r.error_type == "parse_failure"
                            for r in read_results(plan.out_dir / "results.jsonl")))

    def test_non_transient_exception_is_provider_error(self):
        class Broken(FakeGrader):
            def grade(self, namespace, item, request):
                raise RuntimeError("boom " + request.answer)

        plan = self._plan(n=2)
        logged = []
        sink = logger.add(lambda m: logged.append(str(m)), level="WARNING")
        try:
            s = run(plan, Broken(), sleep=lambda s: None)
        finally:
            logger.remove(sink)
        self.assertEqual(2, len(logged))
        self.assertFalse(any("answer" in m for m in logged))
        self.assertEqual({"provider_error": 2}, s.failures)
        results = read_results(plan.out_dir / "results.jsonl")
        self.assertTrue(all(r.error_type == "provider_error" and r.feedback == ""
                            for r in results))

    def test_budget_checked_before_any_call(self):
        plan = self._plan(n=10, price_in_per_mtok=1e6)
        with self.assertRaises(BudgetError):
            run(plan, ExplodingGrader())
        self.assertFalse((plan.out_dir / "results.jsonl").exists())

    def test_zero_budget_zero_price_runs(self):
        s = run(self._plan(n=2, max_cost_usd=0.0), FakeGrader(), sleep=lambda s: None)
        self.assertEqual((2, None, 0.0), (s.graded, s.aborted, s.cost_usd))

    def test_running_cost_cap_stops_submission(self):
        # estimate 10 * 2000 * 1.0 / 1e6 = 0.02 <= 0.03; actual 0.02 per call.
        plan = self._plan(n=10, price_in_per_mtok=1.0, max_cost_usd=0.03, concurrency=1)
        g = FakeGrader(prompt_tokens=20000)
        s = run(plan, g, sleep=lambda s: None)
        self.assertEqual(("budget", 2, 2), (s.aborted, s.graded, g.calls))
        self.assertAlmostEqual(0.04, s.cost_usd)
        self.assertEqual(2, len(read_results(plan.out_dir / "results.jsonl")))
        self.assertNotIn("budget_abort", s.failures)

    def test_plan_refuses_private_dataset_outside_private_dir(self):
        for ds, split in (("engsaf", "dev"), ("jk_case", "case")):
            with self.assertRaises(PrivacyError):
                plan_run(_cfg(datasets={ds: [split]}), {ds: _items(3, dataset=ds, split=split)},
                         self.root)

    def test_run_refuses_private_plan_outside_private_dir(self):
        plan = self._plan(n=2)
        plan.items = _items(2, dataset="engsaf", split="dev")
        plan.config = _cfg(datasets={"engsaf": ["dev"]})
        with self.assertRaises(PrivacyError):
            run(plan, ExplodingGrader(), sleep=lambda s: None)

    def test_plan_allows_private_dataset_under_private_dir(self):
        root = paths.PRIVATE_DIR / "evaluation" / "_runner_test_tmp"
        try:
            plan = plan_run(_cfg(datasets={"engsaf": ["dev"]}),
                            {"engsaf": _items(3, dataset="engsaf", split="dev")}, root)
            self.assertTrue(paths.is_private_path(plan.out_dir))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_summary_written_and_readable(self):
        plan = self._plan(n=2)
        s = run(plan, FakeGrader(), sleep=lambda s: None)
        self.assertIsInstance(s, RunSummary)
        self.assertEqual(s, read_summary(plan.out_dir / "run_summary.json"))
        self.assertTrue(s.started_at.endswith("+00:00"))

    def test_consistency_repeats_expand_and_resume(self):
        items = _items(6, dataset="scientsbank", split="dev")
        cfg = _cfg(datasets={"scientsbank": ["dev"]}, repeats=3, variant_set="consistency")
        plan = plan_run(cfg, {"scientsbank": items}, self.root)
        g = FakeGrader()
        s = run(plan, g, sleep=lambda s: None)
        self.assertEqual(18, s.graded)
        pairs = {(r.item_id, r.repeat) for r in read_results(plan.out_dir / "results.jsonl")}
        self.assertEqual({(i.item_id, k) for i in items for k in range(3)}, pairs)
        s2 = run(plan, FakeGrader(), sleep=lambda s: None)
        self.assertEqual((0, 18), (s2.graded, s2.skipped_existing))

    def test_injection_variant_set_uses_committed_templates(self):
        items = _items(6, dataset="scientsbank", split="dev")
        cfg = _cfg(datasets={"scientsbank": ["dev"]}, variant_set="injection")
        plan = plan_run(cfg, {"scientsbank": items}, self.root)
        originals = [i for i in plan.items if i.derived_from is None]
        copies = [i for i in plan.items if i.derived_from is not None]
        self.assertEqual(2, len(originals))   # gold-0 items: k = 0, 3
        self.assertEqual(6, len(copies))
        run(plan, FakeGrader(), sleep=lambda s: None)
        variants = {r.variant for r in read_results(plan.out_dir / "results.jsonl")}
        self.assertEqual({None, "injection:en:0", "injection:en:1", "injection:en:2"}, variants)


if __name__ == "__main__":
    unittest.main()
