import dataclasses
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.evaluation import metrics, paths
from src.evaluation.experiment import ExperimentConfig
from src.evaluation.report import (
    CITATIONS,
    LIMITATIONS,
    Aggregate,
    MetricRow,
    aggregate,
    build_manifest,
    compare_runs,
    fit_run_thresholds,
    load_report_thresholds,
    load_run,
    render_comparison,
    render_json,
    render_markdown,
    write_report,
)
from src.evaluation.runner import RunSummary
from src.evaluation.schema import EvalResult, RunManifest, append_jsonl
from src.evaluation.stats import Estimate
from src.evaluation.thresholds import Thresholds, apply_thresholds

N = 50  # bootstrap resamples in tests
ENGSAF_CITATION = (
    'Aggarwal, D., Sil, P., Raman, B., Bhattacharyya, P. (2025). "I Understand Why I Got '
    'This Grade": Automatic Short Answer Grading (ASAG) with Feedback. In: Artificial '
    'Intelligence in Education. AIED 2025. Lecture Notes in Computer Science, vol 15879. '
    'Springer, Cham. https://doi.org/10.1007/978-3-031-98420-4_22')
SEMEVAL_CITATION = (
    "Dzikovska et al. (2013). SemEval-2013 Task 7: The Joint Student Response Analysis and "
    "8th Recognizing Textual Entailment Challenge. In Proceedings of the Seventh "
    "International Workshop on Semantic Evaluation (SemEval 2013), pp. 263–274, ACL.")
SCIENTSBANK_CITATION = (
    "Nielsen, Ward, Martin & Palmer (2008). Annotating students' understanding of science "
    "concepts (SciEntsBank). LREC 2008. Licensed CC BY 4.0 via HF nkazi/SciEntsBank.")
LIMITATION_TEXT = [
    "Materials are the datasets' reference answers, not real course materials; "
    "real-course retrieval may be harder.",
    "EngSAF feedback is LLM-generated and is not used as a gold standard; only its labels are.",
    "The Indonesian case study has 32 answers from 4 questions and is reported "
    "qualitatively, without statistical claims.",
    "The no_context bound uses a single placeholder document ('No course materials are "
    "available'), because the product refuses to grade with zero retrieved documents.",
    "Provider routing is outside the configuration file; the served provider per call is "
    "recorded and reported.",
    "The oracle and no_context bounds exclude the case study, whose reference is a PDF.",
]


def _cfg(**kw):
    base = dict(
        name="rep", phase="4a", grader="stub", model="m/x", provider="openrouter",
        context_mode="rag", temperature=None,
        datasets={"scientsbank": ["dev", "test_ua"]}, repeats=1, variant_set=None,
        price_in_per_mtok=0.0, price_out_per_mtok=0.0, concurrency=1, max_cost_usd=0.0,
        overrides={},
    )
    base.update(kw)
    return ExperimentConfig(**base)


def _res(i, dataset="scientsbank", split="dev", gold=None, score=None, **kw):
    gold = i % 3 if gold is None else gold
    score = (gold * 38 + (i * 7) % 25) if score is None else score
    base = dict(
        item_id=f"{dataset}-{split}-{i}", config_hash="h1", dataset=dataset,
        question_id=f"qid-{i % 5}", split=split, gold_label=gold, success=True,
        score=float(score), confidence=0.5 + (i % 5) / 10, citations_kept=1,
        citations_dropped=i % 2, retrieved_sources=(f"src{i % 5}", "srcX"),
        gold_source=f"src{i % 5}", provider="p1",
        gold_label_raw="correct" if gold == 2 else "partially_correct_incomplete",
    )
    base.update(kw)
    return EvalResult(**base)


def _sci_results():
    return ([_res(i, split="dev") for i in range(40)]
            + [_res(i, split="test_ua") for i in range(30)])


def _summary():
    return RunSummary(out_dir=Path("x"), graded=70, skipped_existing=0, failures={},
                      cost_usd=0.0, tokens_in=0, tokens_out=0, aborted=None,
                      started_at="2026-11-23T00:00:00+00:00",
                      finished_at="2026-11-23T00:01:00+00:00")


def _row(agg, dataset, split, metric):
    for r in agg.rows:
        if (r.dataset, r.split, r.metric) == (dataset, split, metric):
            return r.estimate
    raise KeyError((dataset, split, metric))


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.results = _sci_results()
        self.cfg = _cfg()
        self.ths = fit_run_thresholds(self.results, self.cfg.datasets)
        self.agg = aggregate(self.results, self.cfg, self.ths, n_resamples=N)

    def test_thresholds_fitted_on_dev_only(self):
        self.assertIn("scientsbank", self.ths)
        self.assertEqual("scientsbank/dev", self.ths["scientsbank"].fitted_on)

    def test_qwk_matches_metrics_on_same_labels(self):
        th = self.ths["scientsbank"]
        for split in ("dev", "test_ua"):
            rows = [r for r in self.results if r.split == split]
            want = metrics.qwk([r.gold_label for r in rows],
                               [apply_thresholds(r.score, th) for r in rows], 3)
            self.assertAlmostEqual(want, _row(self.agg, "scientsbank", split, "qwk").value)

    def test_failures_excluded_from_agreement_and_counted(self):
        bad = [_res(100 + i, success=False, score=None, confidence=None,
                    error_type="parse_failure") for i in range(4)]
        agg = aggregate(self.results + bad, self.cfg, self.ths, n_resamples=N)
        self.assertAlmostEqual(_row(self.agg, "scientsbank", "dev", "qwk").value,
                               _row(agg, "scientsbank", "dev", "qwk").value)
        self.assertEqual({"parse_failure": 4}, agg.failures)
        self.assertAlmostEqual(4 / 44, _row(agg, "scientsbank", "dev",
                                            "parse_failure_rate").value)

    def test_two_way_and_retrieval_and_reliability(self):
        th = self.ths["scientsbank"]
        rows = [r for r in self.results if r.split == "dev"]
        pred = [r.score >= th.t2 for r in rows]
        gold = [r.gold_label_raw == "correct" for r in rows]
        self.assertAlmostEqual(metrics.accuracy(gold, pred),
                               _row(self.agg, "scientsbank", "dev", "accuracy_2way").value)
        self.assertEqual(1.0, _row(self.agg, "scientsbank", "dev", "hit_at_1").value)
        self.assertEqual(1.0, _row(self.agg, "scientsbank", "dev", "mrr").value)
        kept = sum(r.citations_kept for r in rows)
        dropped = sum(r.citations_dropped for r in rows)
        self.assertAlmostEqual(kept / (kept + dropped),
                               _row(self.agg, "scientsbank", "dev", "grounded_share").value)
        self.assertEqual(5, _row(self.agg, "scientsbank", "dev", "qwk").n_clusters)

    def test_no_retrieval_rows_without_rag(self):
        agg = aggregate(self.results, _cfg(context_mode="oracle"), self.ths, n_resamples=N)
        self.assertFalse([r for r in agg.rows if r.metric in ("hit_at_1", "mrr")])

    def test_providers_counted(self):
        self.assertEqual({"p1": 70}, self.agg.extra["providers"])

    def test_aggregate_holds_no_strings_from_results(self):
        blob = json.dumps(render_json(self.agg, RunManifest()))
        self.assertNotIn("qid-", blob)
        self.assertNotIn("src1", blob)
        self.assertNotIn("partially_correct", blob)


class ThresholdFailureTests(unittest.TestCase):
    def test_constant_dev_records_error_and_report_says_so(self):
        results = [_res(i, gold=1) for i in range(20)]
        cfg = _cfg(datasets={"scientsbank": ["dev"]})
        ths = fit_run_thresholds(results, cfg.datasets)
        self.assertNotIn("scientsbank", ths)
        self.assertIn("scientsbank", ths.errors)
        agg = aggregate(results, cfg, ths, n_resamples=N)
        self.assertTrue(math.isnan(_row(agg, "scientsbank", "dev", "qwk").value))
        md = render_markdown(agg, RunManifest())
        self.assertIn("thresholds could not be fitted", md)
        self.assertIn("n/a", md)
        js = render_json(agg, RunManifest())
        self.assertIsNone(js["metrics"]["scientsbank"]["dev"]["qwk"]["value"])
        json.dumps(js, allow_nan=False)

    def test_no_thresholds_for_case_study(self):
        results = [_res(i, dataset="jk_case", split="case", gold_score=0.5) for i in range(8)]
        ths = fit_run_thresholds(results, {"jk_case": ["case"]})
        self.assertEqual({}, dict(ths))


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.results = _sci_results()
        self.cfg = _cfg()
        self.ths = fit_run_thresholds(self.results, self.cfg.datasets)
        self.agg = aggregate(self.results, self.cfg, self.ths, n_resamples=N)
        self.manifest = RunManifest(config_hash="h1", model="m/x")

    def test_json_top_level_keys_and_shape(self):
        js = render_json(self.agg, self.manifest)
        self.assertEqual({"manifest", "metrics", "counts", "failures", "thresholds", "extra"},
                         set(js))
        cell = js["metrics"]["scientsbank"]["dev"]["qwk"]
        self.assertEqual({"value", "low", "high", "n_items", "n_clusters"}, set(cell))
        self.assertEqual(self.ths["scientsbank"].t1, js["thresholds"]["scientsbank"]["t1"])
        json.dumps(js, allow_nan=False)

    def test_sections_in_order_and_fixed_text_verbatim(self):
        md = render_markdown(self.agg, self.manifest)
        headings = ["## Manifest", "## Data and cleaning counts", "## Thresholds",
                    "## Agreement", "## SciEntsBank 2-way", "## Retrieval", "## Calibration",
                    "## Reliability", "## Case study", "## Variants", "## Limitations",
                    "## Citations"]
        pos = [md.index(h) for h in headings]
        self.assertEqual(sorted(pos), pos)
        self.assertTrue(md.startswith("# "))
        for text in LIMITATION_TEXT + [ENGSAF_CITATION, SEMEVAL_CITATION, SCIENTSBANK_CITATION]:
            self.assertIn(text, md)
        self.assertEqual(LIMITATION_TEXT, list(LIMITATIONS))
        self.assertEqual([ENGSAF_CITATION, SEMEVAL_CITATION, SCIENTSBANK_CITATION],
                         list(CITATIONS))

    def test_nan_renders_as_na(self):
        nan = float("nan")
        agg = Aggregate(rows=[MetricRow("scientsbank", "dev", "qwk",
                                        Estimate(nan, nan, nan, 0, 0, 0))],
                        counts={}, failures={}, thresholds={}, extra={})
        md = render_markdown(agg, RunManifest())
        self.assertIn("n/a", md)
        self.assertNotIn("nan", md)
        self.assertIsNone(render_json(agg, RunManifest())["metrics"]["scientsbank"]["dev"]
                          ["qwk"]["low"])

    def test_single_provider_no_warning(self):
        md = render_markdown(self.agg, self.manifest)
        self.assertNotIn("More than one provider", md)

    def test_two_providers_produce_warning_and_table(self):
        results = [dataclasses.replace(r, provider="p2") if i % 2 else r
                   for i, r in enumerate(self.results)]
        agg = aggregate(results, self.cfg, self.ths, n_resamples=N)
        self.assertEqual({"p1": 35, "p2": 35}, agg.extra["providers"])
        md = render_markdown(agg, self.manifest)
        self.assertIn("More than one provider served this run", md)
        self.assertIn("| p2 |", md)

    def test_write_report_writes_md_and_json(self):
        d = Path(tempfile.mkdtemp())
        try:
            md, js = write_report(self.agg, self.manifest, d / "2026-11-23-4a-rep")
            self.assertEqual((".md", ".json"), (md.suffix, js.suffix))
            self.assertEqual(render_json(self.agg, self.manifest),
                             json.loads(js.read_text(encoding="utf-8")))
            self.assertIn("## Citations", md.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class CaseStudyAndVariantTests(unittest.TestCase):
    def test_case_study_questions_labelled_by_sorted_id(self):
        qids = ["zeta question text", "alpha question text", "mid question", "beta"]
        results = []
        for k, q in enumerate(qids):
            for j in range(8):
                results.append(_res(k * 8 + j, dataset="jk_case", split="case",
                                    question_id=q, score=40.0 + k, gold_score=0.4))
        cfg = _cfg(datasets={"jk_case": ["case"]})
        agg = aggregate(results, cfg, fit_run_thresholds(results, cfg.datasets),
                        n_resamples=N)
        # sorted: alpha(k=1), beta(k=3), mid(k=2), zeta(k=0); points = score/4, gold = 10
        expect = {"Q1": abs(41 / 4 - 10), "Q2": abs(43 / 4 - 10), "Q3": abs(42 / 4 - 10),
                  "Q4": abs(40 / 4 - 10)}
        for q, v in expect.items():
            self.assertAlmostEqual(v, _row(agg, "jk_case", "case", f"mae_points_{q}").value)
        md = render_markdown(agg, RunManifest())
        blob = md + json.dumps(render_json(agg, RunManifest()))
        for q in qids:
            self.assertNotIn(q, blob)
        self.assertIn("Q4", md)

    def test_consistency_metrics(self):
        results = []
        for i in range(10):
            for rep in range(3):
                results.append(_res(i, repeat=rep, score=50.0 + (rep if i % 2 else 0)))
        cfg = _cfg(datasets={"scientsbank": ["dev"]}, repeats=3, variant_set="consistency")
        ths = {"scientsbank": Thresholds(30.0, 70.0, "scientsbank/dev", 0.5)}
        agg = aggregate(results, cfg, ths, n_resamples=N)
        std_odd = math.sqrt(2 / 3)
        self.assertAlmostEqual(std_odd / 2,
                               _row(agg, "scientsbank", "dev", "consistency_score_std").value)
        self.assertEqual(1.0, _row(agg, "scientsbank", "dev",
                                   "consistency_label_agreement").value)
        self.assertEqual(10, _row(agg, "scientsbank", "dev", "qwk").n_items)
        self.assertIn("Consistency", render_markdown(agg, RunManifest()))

    def test_injection_metrics(self):
        results = []
        for i in range(6):
            orig = _res(i, gold=0, score=10.0)
            results.append(orig)
            for k in range(2):
                results.append(_res(i, gold=0, item_id=f"{orig.item_id}::inj{k}",
                                    derived_from=orig.item_id, variant=f"injection:en:{k}",
                                    score=10.0 + (50 if k else 0),
                                    integrity_warnings=(
                                        ("possible_prompt_injection:override",) if k else ())))
        cfg = _cfg(datasets={"scientsbank": ["dev"]}, variant_set="injection")
        ths = {"scientsbank": Thresholds(30.0, 70.0, "scientsbank/dev", 0.5)}
        agg = aggregate(results, cfg, ths, n_resamples=N)
        self.assertAlmostEqual(25.0, _row(agg, "scientsbank", "dev",
                                          "injection_score_uplift").value)
        self.assertAlmostEqual(0.5, _row(agg, "scientsbank", "dev",
                                         "injection_label_rise_share").value)
        self.assertAlmostEqual(0.5, _row(agg, "scientsbank", "dev",
                                         "injection_detection_rate").value)
        self.assertEqual(6, _row(agg, "scientsbank", "dev", "qwk").n_items)
        self.assertIn("Injection", render_markdown(agg, RunManifest()))


def _injection_results():
    results = []
    for i in range(6):
        orig = _res(i, gold=0, score=10.0)
        results.append(orig)
        for k in range(2):
            results.append(_res(i, gold=0, item_id=f"{orig.item_id}::inj{k}",
                                derived_from=orig.item_id, variant=f"injection:en:{k}",
                                score=10.0 + (50 if k else 0)))
    return results


class FrozenThresholdTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        base = _sci_results()
        cfg = _cfg(datasets={"scientsbank": ["dev"]})
        ths = fit_run_thresholds(base, cfg.datasets)
        self.baseline_ths = ths["scientsbank"]
        agg = aggregate(base, cfg, ths, n_resamples=N)
        _, self.baseline_json = write_report(agg, RunManifest(), self.dir / "baseline")
        self.inj_cfg = _cfg(datasets={"scientsbank": ["dev"]}, variant_set="injection")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_load_report_thresholds_round_trips(self):
        loaded = load_report_thresholds(self.baseline_json)
        self.assertEqual({"scientsbank": self.baseline_ths}, dict(loaded))
        self.assertEqual("baseline.json", loaded.source)

    def test_load_report_thresholds_relative_to_repo(self):
        target = paths.PRIVATE_DIR / "evaluation" / "_thresholds_test.json"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.baseline_json, target)
            self.assertEqual("private-data/evaluation/_thresholds_test.json",
                             load_report_thresholds(target).source)
        finally:
            target.unlink(missing_ok=True)

    def test_injection_without_override_has_na_label_rise_and_note(self):
        results = _injection_results()
        ths = fit_run_thresholds(results, self.inj_cfg.datasets)
        self.assertIn("scientsbank", ths.errors)   # gold-0 only: cannot fit
        agg = aggregate(results, self.inj_cfg, ths, n_resamples=N)
        self.assertTrue(math.isnan(_row(agg, "scientsbank", "dev",
                                        "injection_label_rise_share").value))
        self.assertIn("--thresholds-from", render_markdown(agg, RunManifest()))

    def test_injection_with_frozen_thresholds_has_label_rise(self):
        results = _injection_results()
        frozen = load_report_thresholds(self.baseline_json)
        ths = fit_run_thresholds(results, self.inj_cfg.datasets)
        agg = aggregate(results, self.inj_cfg, ths, n_resamples=N, thresholds_override=frozen)
        rise = _row(agg, "scientsbank", "dev", "injection_label_rise_share").value
        self.assertFalse(math.isnan(rise))
        self.assertAlmostEqual(0.5, rise)
        self.assertEqual({}, agg.extra["threshold_errors"])
        self.assertEqual(self.baseline_ths, agg.thresholds["scientsbank"])
        js = render_json(agg, RunManifest())
        self.assertEqual("baseline.json", js["extra"]["thresholds_source"])
        md = render_markdown(agg, RunManifest())
        self.assertNotIn("--thresholds-from", md)
        self.assertIn("baseline.json", md)

    def test_manifest_records_thresholds_source(self):
        frozen = load_report_thresholds(self.baseline_json)
        with mock.patch("src.evaluation.report.subprocess.run", side_effect=FileNotFoundError):
            m = build_manifest(self.inj_cfg, "h1", _summary(), {}, {}, thresholds=frozen)
        self.assertEqual("baseline.json", m.thresholds_source)
        self.assertEqual(self.baseline_ths.t1, m.thresholds["scientsbank"]["t1"])


class MinorFixTests(unittest.TestCase):
    def test_case_study_requires_gold_score(self):
        results = [_res(i, dataset="jk_case", split="case") for i in range(4)]
        with self.assertRaises(ValueError):
            aggregate(results, _cfg(datasets={"jk_case": ["case"]}), {}, n_resamples=N)

    def test_agreement_n_counts_scored_rows_only(self):
        results = _sci_results() + [
            _res(100 + i, success=False, score=None, confidence=None,
                 error_type="parse_failure") for i in range(4)]
        cfg = _cfg(datasets={"scientsbank": ["dev"]})
        agg = aggregate(results, cfg, fit_run_thresholds(results, cfg.datasets),
                        n_resamples=N)
        self.assertEqual(40, _row(agg, "scientsbank", "dev", "qwk").n_items)
        self.assertEqual(44, _row(agg, "scientsbank", "dev", "failure_rate").n_items)
        md = render_markdown(agg, RunManifest())
        section = md[md.index("## Agreement"):md.index("## SciEntsBank 2-way")]
        dev_line = [l for l in section.splitlines() if l.startswith("| scientsbank | dev")][0]
        self.assertTrue(dev_line.endswith("| 40 |"), dev_line)

    def test_case_study_kept_out_of_ci_tables(self):
        results = _sci_results() + [
            _res(i, dataset="jk_case", split="case", gold_score=0.5) for i in range(8)]
        cfg = _cfg(datasets={"scientsbank": ["dev", "test_ua"], "jk_case": ["case"]})
        agg = aggregate(results, cfg, fit_run_thresholds(results, cfg.datasets),
                        n_resamples=N)
        md = render_markdown(agg, RunManifest())
        tables = md[md.index("## Agreement"):md.index("## Case study")]
        self.assertNotIn("| jk_case |", tables)
        js = render_json(agg, RunManifest())
        self.assertIn("grounded_share", js["metrics"]["jk_case"]["case"])


class CompareAndLoadTests(unittest.TestCase):
    def test_compare_with_itself_is_no_detectable_difference(self):
        results = _sci_results()
        ths = fit_run_thresholds(results, {"scientsbank": ["dev", "test_ua"]})
        rows = compare_runs(results, results, ths, ths, n_resamples=N)
        self.assertEqual(6, len(rows))
        self.assertEqual({"no detectable difference"}, {r[4] for r in rows})
        self.assertEqual({("scientsbank", "dev"), ("scientsbank", "test_ua")},
                         {(r[0], r[1]) for r in rows})

    def test_compare_undefined_renders_na_undefined(self):
        results = [_res(i, gold=1) for i in range(20)]
        rows = compare_runs(results, results, {}, {}, n_resamples=N)
        qwk_rows = [r for r in rows if r[2] == "qwk"]
        self.assertEqual("undefined", qwk_rows[0][4])
        text = render_comparison(rows)
        self.assertIn("n/a (undefined)", text)

    def test_load_run_rejects_mixed_hashes(self):
        d = Path(tempfile.mkdtemp())
        try:
            append_jsonl(d / "results.jsonl", _res(1))
            append_jsonl(d / "results.jsonl", _res(2, config_hash="h2"))
            with self.assertRaises(ValueError):
                load_run(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_load_run_reads_results_and_summary(self):
        from src.evaluation.runner import _write_summary
        d = Path(tempfile.mkdtemp())
        try:
            append_jsonl(d / "results.jsonl", _res(1))
            s = dataclasses.replace(_summary(), out_dir=d)
            _write_summary(s)
            results, summary = load_run(d)
            self.assertEqual(1, len(results))
            self.assertEqual(s, summary)
        finally:
            shutil.rmtree(d, ignore_errors=True)


def _paired_runs(dataset="engsaf", split="test"):
    """A is off by 40 points on every item, B is exact."""
    import random
    rng = random.Random(1)
    a, b = [], []
    for q in range(20):
        for i in range(5):
            g = rng.choice([0, 1, 2])
            common = dict(item_id=f"i{q}-{i}", dataset=dataset, question_id=f"q{q}",
                          split=split, gold_label=g, success=True, confidence=0.5,
                          gold_score=(g / 2 if dataset == "jk_case" else None))
            a.append(EvalResult(config_hash="a", score=float(max(0, min(100, g * 50 + rng.choice(
                [-40, 40])))), **common))
            b.append(EvalResult(config_hash="b", score=float(g * 50), **common))
    return a, b


class InjectionReportTests(unittest.TestCase):
    def test_injection_report_suppresses_agreement_and_calibration_tables(self):
        cfg = _cfg(datasets={"scientsbank": ["dev"]}, variant_set="injection")
        ths = {"scientsbank": Thresholds(30.0, 70.0, "scientsbank/dev", 0.5)}
        md = render_markdown(aggregate(_injection_results(), cfg, ths, n_resamples=N),
                             RunManifest())
        agreement = md.split("## Agreement")[1].split("## ")[0]
        calibration = md.split("## Calibration")[1].split("## ")[0]
        for section in (agreement, calibration):
            self.assertIn("Not reported for injection runs", section)
            self.assertNotIn("| Dataset |", section)
        self.assertIn("### Injection", md)
        base = render_markdown(aggregate(_injection_results(), _cfg(datasets={
            "scientsbank": ["dev"]}), ths, n_resamples=N), RunManifest())
        self.assertIn("| Dataset | Split | qwk", base)


class CompareDirectionTests(unittest.TestCase):
    def test_lower_is_better_metric_decrease_improves(self):
        a, b = _paired_runs()
        th = {"engsaf": Thresholds(25.0, 75.0, "engsaf/dev", 0.0)}
        rows = {r[2]: r for r in compare_runs(a, b, th, th, n_resamples=N)}
        self.assertLess(rows["mae_score"][3].value, 0)
        self.assertEqual("improves", rows["mae_score"][4])
        self.assertEqual("improves", rows["qwk"][4])
        # And the reverse direction worsens.
        rev = {r[2]: r for r in compare_runs(b, a, th, th, n_resamples=N)}
        self.assertEqual("worsens", rev["mae_score"][4])

    def test_metric_directions(self):
        from src.evaluation.report import higher_is_better
        for m in ("mae_score", "mae_label", "mae_points", "mae_points_Q1", "ece",
                  "failure_rate", "parse_failure_rate"):
            self.assertFalse(higher_is_better(m), m)
        for m in ("qwk", "accuracy", "spearman", "hit_at_1"):
            self.assertTrue(higher_is_better(m), m)

    def test_case_study_compare_is_descriptive_only(self):
        a, b = _paired_runs(dataset="jk_case", split="case")
        rows = compare_runs(a, b, {}, {}, metrics=("mae_score",), n_resamples=N)
        self.assertEqual(1, len(rows))
        ds, split, metric, est, verdict = rows[0]
        self.assertEqual("case study: descriptive only", verdict)
        self.assertLess(est.value, 0)
        self.assertTrue(math.isnan(est.low) and math.isnan(est.high))
        text = render_comparison(rows)
        self.assertIn("case study: descriptive only", text)
        self.assertNotIn("[", text.split("\n")[-2])  # no interval on the case row

    def test_compare_counts_per_side_failures_and_dropped_pairs(self):
        from src.evaluation.report import compare_counts
        a, b = _paired_runs()
        a[0] = dataclasses.replace(a[0], success=False, score=None, error_type="parse_failure")
        b[1] = dataclasses.replace(b[1], success=False, score=None, error_type="provider_error")
        b[2] = dataclasses.replace(b[2], success=False, score=None, error_type="provider_error")
        b = b[:-1]  # one item only in A
        counts = compare_counts(a, b)
        self.assertEqual({"a_results": 100, "a_failures": 1, "b_results": 99, "b_failures": 2,
                          "paired": 96, "pairs_dropped": 3, "unmatched": 1},
                         counts[("engsaf", "test")])
        text = render_comparison(compare_runs(a, b, {}, {}, n_resamples=N), counts)
        self.assertIn("A failures", text)
        self.assertIn("| engsaf | test | 100 | 1 | 99 | 2 | 96 | 3 | 1 |", text)


class ManifestTests(unittest.TestCase):
    def test_build_manifest_fields(self):
        from src import __version__
        from src.evaluation.experiment import prompt_template_hash
        from src.evaluation.splits import SplitFile
        cfg = _cfg(temperature=0.0)
        split = SplitFile("scientsbank", "snap", 20261123, {"dev": ["a", "b"]},
                          {"dev": []}, {"dev": 2})
        ths = {"scientsbank": Thresholds(30.0, 70.0, "scientsbank/dev", 0.5)}

        def fake_run(args, **kw):
            out = "abc123\n" if args[:2] == ["git", "rev-parse"] else " M file\n"
            return mock.Mock(returncode=0, stdout=out)

        with mock.patch("src.evaluation.report.subprocess.run", side_effect=fake_run):
            m = build_manifest(cfg, "h1", _summary(), {"scientsbank": split},
                               {"scientsbank": "snap"}, embedding_model="BAAI/bge-m3",
                               thresholds=ths,
                               config_file=paths.EVAL_ASSETS / "experiments" / "x.yaml",
                               results=_sci_results())
        self.assertEqual(("abc123", True), (m.git_sha, m.git_dirty))
        self.assertEqual(__version__, m.backend_version)
        self.assertEqual(prompt_template_hash(), m.prompt_template_sha256)
        self.assertEqual("backend/evaluation/experiments/x.yaml", m.config_file)
        self.assertEqual(("m/x", "openrouter", 0.0, "BAAI/bge-m3"),
                         (m.model, m.provider, m.temperature, m.embedding_model))
        self.assertEqual({"scientsbank": "snap"}, m.dataset_snapshots)
        self.assertEqual(64, len(m.split_hashes["scientsbank"]))
        self.assertEqual({"scientsbank": {"dev": 2}}, m.item_counts)
        self.assertEqual(30.0, m.thresholds["scientsbank"]["t1"])
        self.assertEqual(70, m.calls)
        self.assertEqual("2026-11-23T00:00:00+00:00", m.started_at)

    def test_git_unavailable_gives_none(self):
        with mock.patch("src.evaluation.report.subprocess.run", side_effect=FileNotFoundError):
            m = build_manifest(_cfg(), "h1", _summary(), {}, {})
        self.assertIsNone(m.git_sha)
        self.assertIsNone(m.git_dirty)


if __name__ == "__main__":
    unittest.main()
