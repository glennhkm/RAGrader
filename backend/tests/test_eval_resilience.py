"""Pacing, transient classification, circuit breaker and --retry-failed."""

import dataclasses
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.evaluation.experiment import config_hash, load_experiment
from src.evaluation.graders.base import TransientGraderError
from src.evaluation.graders.inprocess import InProcessGrader, _is_transient
from src.evaluation.graders.pacing import RateLimiter
from src.evaluation.runner import plan_run, run
from src.evaluation.schema import read_results
from test_eval_runner import FakeGrader, _cfg, _items, _ok


class RateLimiterTest(unittest.TestCase):
    def test_spaces_calls_evenly(self):
        now, slept = [0.0], []

        def sleep(s):
            slept.append(round(s, 6))
            now[0] += s

        limiter = RateLimiter(30, clock=lambda: now[0], sleep=sleep)
        for _ in range(3):
            limiter.wait()
        self.assertEqual([2.0, 2.0], slept)


class TransientTest(unittest.TestCase):
    def test_gateway_and_network_errors_are_transient(self):
        for text in ("Error code: 413 - request too large", "Connection error.",
                     "Connection reset by peer", "code: upstream_error"):
            self.assertTrue(_is_transient(text), text)
        for text in ("invalid api key", "No relevant materials retrieved"):
            self.assertFalse(_is_transient(text), text)


class PacedGraderTest(unittest.TestCase):
    def test_llm_and_embedding_calls_share_one_limiter(self):
        waits = []
        g = InProcessGrader.__new__(InProcessGrader)
        g._limiter = SimpleNamespace(wait=lambda: waits.append(1))
        emb = SimpleNamespace(embed_query=lambda t: [1.0],
                              embed_documents=lambda ts: [[1.0] for _ in ts])
        llm = SimpleNamespace(generate=lambda p: "out")
        g._pace(llm, emb)
        llm.generate("p"), emb.embed_query("q"), emb.embed_documents(["a", "b"])
        self.assertEqual(3, len(waits))

    def test_requests_per_minute_is_validated_and_not_hashed(self):
        a, b = _cfg(), _cfg(requests_per_minute=30)
        self.assertEqual(config_hash(a, {}), config_hash(b, {}))
        text = ("name: x\nphase: 4a\ngrader: stub\nprovider: stub\n"
                "datasets: {synthetic: [smoke]}\nrequests_per_minute: 0\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.yaml"
            p.write_text(text)
            with self.assertRaisesRegex(ValueError, "requests_per_minute"):
                load_experiment(p)


class Down(FakeGrader):
    def grade(self, namespace, item, request):
        with self._lock:
            self.calls += 1
        raise TransientGraderError("503")


class ResilienceTest(unittest.TestCase):
    def _plan(self, n):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return plan_run(_cfg(concurrency=1), {"synthetic": _items(n)}, Path(tmp.name))

    def test_breaker_stops_after_consecutive_give_ups(self):
        plan = self._plan(20)
        s = run(plan, Down(), sleep=lambda _: None, max_attempts=2)
        self.assertEqual("provider_unavailable", s.aborted)
        self.assertEqual(5, s.graded)

    def test_retry_failed_regrades_only_infrastructure_failures(self):
        plan = self._plan(20)
        run(plan, Down(), sleep=lambda _: None, max_attempts=1)
        plain = run(dataclasses.replace(plan, items=plan.items[:5]), FakeGrader(),
                    sleep=lambda _: None)
        self.assertEqual((0, 5), (plain.graded, plain.skipped_existing))
        s = run(plan, FakeGrader(), sleep=lambda _: None, retry_failed=True)
        self.assertEqual((None, 20, {}), (s.aborted, s.graded, s.failures))
        rows = read_results(plan.out_dir / "results.jsonl")
        self.assertEqual(20, len({r.item_id for r in rows}))
        self.assertEqual(20, len(rows))

    def test_retry_failed_keeps_parse_failures(self):
        class Parse(FakeGrader):
            def grade(self, namespace, item, request):
                raw = _ok()
                raw.success, raw.score, raw.error_type = False, None, "parse_failure"
                return raw

        plan = self._plan(3)
        run(plan, Parse(), sleep=lambda _: None)
        s = run(plan, FakeGrader(), sleep=lambda _: None, retry_failed=True)
        self.assertEqual((0, 3), (s.graded, s.skipped_existing))


if __name__ == "__main__":
    unittest.main()
