"""Aggregate evaluation reports (Markdown + JSON) with a run manifest (spec sections 6.4, 6.5, 6.7).

Privacy by construction: ``aggregate`` turns results into an ``Aggregate`` that holds only
numbers, counts, dataset/split/metric names and fixed strings. Question ids, source names,
feedback and every other per-item string stay inside private helpers and never reach it.
``render_markdown`` and ``render_json`` read only an ``Aggregate`` and a ``RunManifest``,
so per-item text has no code path into a report. Case-study questions appear as ``Q1..Q4``
(sorted ``question_id`` order), never by id or text.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import statistics
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import metrics as M
from .experiment import ExperimentConfig, prompt_template_hash
from .paths import REPO_ROOT
from .privacy import PrivacyError, assert_output_allowed
from .runner import RESULTS_FILE, SUMMARY_FILE, RunSummary, read_summary
from .schema import EvalResult, RunManifest, read_results
from .splits import SplitFile
from .stats import Estimate, cluster_bootstrap, describe_difference, paired_difference
from .thresholds import Thresholds, apply_thresholds, case_study_label, fit_thresholds

__all__ = [
    "Aggregate", "CITATIONS", "FittedThresholds", "LIMITATIONS", "MetricRow", "PrivacyError",
    "aggregate", "assert_output_allowed", "build_manifest", "compare_counts", "compare_runs",
    "fit_run_thresholds", "load_report_thresholds", "load_run", "render_comparison", "render_json", "render_markdown",
    "higher_is_better", "write_report",
]

NAN = float("nan")
N_RESAMPLES = 2000
SEED = 20261123
N_LABELS = 3
CASE_STUDY = "jk_case"
CASE_STUDY_VERDICT = "case study: descriptive only"
INJECTION_WARNING = "possible_prompt_injection"

LIMITATIONS: Tuple[str, ...] = (
    "Materials are the datasets' reference answers, not real course materials; "
    "real-course retrieval may be harder.",
    "EngSAF feedback is LLM-generated and is not used as a gold standard; only its labels are.",
    "The Indonesian case study has 32 answers from 4 questions and is reported "
    "qualitatively, without statistical claims.",
    "The no_context bound uses a single placeholder document ('No course materials are "
    "available'), because the product refuses to grade with zero retrieved documents.",
    "OpenRouter provider order is not pinned in 4a; the served provider per call is "
    "recorded and reported.",
    "The oracle and no_context bounds exclude the case study, whose reference is a PDF.",
)

CITATIONS: Tuple[str, ...] = (
    'Aggarwal, D., Sil, P., Raman, B., Bhattacharyya, P. (2025). "I Understand Why I Got '
    'This Grade": Automatic Short Answer Grading (ASAG) with Feedback. In: Artificial '
    'Intelligence in Education. AIED 2025. Lecture Notes in Computer Science, vol 15879. '
    'Springer, Cham. https://doi.org/10.1007/978-3-031-98420-4_22',
    "Dzikovska et al. (2013). SemEval-2013 Task 7: The Joint Student Response Analysis and "
    "8th Recognizing Textual Entailment Challenge. In Proceedings of the Seventh "
    "International Workshop on Semantic Evaluation (SemEval 2013), pp. 263–274, ACL.",
    "Nielsen, Ward, Martin & Palmer (2008). Annotating students' understanding of science "
    "concepts (SciEntsBank). LREC 2008. Licensed CC BY 4.0 via HF nkazi/SciEntsBank.",
)

ERR_NO_DEV = "no successful dev results in this run"
ERR_CONSTANT = "dev labels or scores are constant"


@dataclass(frozen=True)
class MetricRow:
    dataset: str
    split: str
    metric: str
    estimate: Estimate


@dataclass
class Aggregate:
    """Numbers and fixed strings only (see module docstring)."""

    rows: List[MetricRow]
    counts: Dict[str, Dict[str, int]]
    failures: Dict[str, int]
    thresholds: Dict[str, Thresholds]
    extra: Dict[str, Any]


class FittedThresholds(dict):
    """``{dataset: Thresholds}``.

    ``errors`` maps datasets that could not be fitted to a fixed reason. ``source`` is set
    when the thresholds are frozen ones loaded from a baseline report (repo-relative path).
    """

    def __init__(self, *args, errors: Optional[Dict[str, str]] = None,
                 source: Optional[str] = None, **kw):
        super().__init__(*args, **kw)
        self.errors: Dict[str, str] = dict(errors or {})
        self.source: Optional[str] = source


# --------------------------------------------------------------------------- per-item rows
# _Row is internal: it holds per-item ids and source names for the metric functions, and is
# never stored in an Aggregate.

@dataclass(frozen=True)
class _Row:
    key: str
    cluster: str
    success: bool
    error_type: Optional[str]
    label: Optional[int]
    gold: int
    score: Optional[float]      # 0-100
    gold01: float
    confidence: Optional[float]
    warned: bool
    kept: int
    dropped: int
    ranked: Tuple[str, ...]
    gold_source: Optional[str]
    two_pred: Optional[bool]
    two_gold: bool


def _is_base(r: EvalResult) -> bool:
    return r.derived_from is None and r.variant is None


def _label(r: EvalResult, ths: Dict[str, Thresholds]) -> Optional[int]:
    if not r.success or r.score is None:
        return None
    if r.dataset == CASE_STUDY:
        return case_study_label(r.score)
    th = ths.get(r.dataset)
    return apply_thresholds(r.score, th) if th is not None else None


def _to_row(r: EvalResult, ths: Dict[str, Thresholds], cluster: Optional[str] = None) -> _Row:
    scored = r.success and r.score is not None
    th = ths.get(r.dataset)
    two_pred = (r.score >= th.t2) if (scored and th is not None
                                      and r.dataset == "scientsbank") else None
    if r.gold_score is not None:
        gold01 = r.gold_score
    elif r.dataset == CASE_STUDY:
        raise ValueError("case-study result without gold_score")
    else:
        gold01 = r.gold_label / (N_LABELS - 1)
    return _Row(
        key=f"{r.item_id}#{r.repeat}", cluster=cluster or r.question_id, success=scored,
        error_type=r.error_type, label=_label(r, ths), gold=r.gold_label,
        score=r.score if scored else None, gold01=float(gold01), confidence=r.confidence,
        warned=bool(r.integrity_warnings), kept=r.citations_kept, dropped=r.citations_dropped,
        ranked=tuple(r.retrieved_sources), gold_source=r.gold_source, two_pred=two_pred,
        two_gold=r.gold_label_raw == "correct",
    )


def _ok(rows: Sequence[_Row]) -> List[_Row]:
    return [x for x in rows if x.success]


def _lab(rows: Sequence[_Row]) -> List[_Row]:
    return [x for x in rows if x.success and x.label is not None]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else NAN


def _ratio(num: float, den: float) -> float:
    return num / den if den else NAN


def _two(rows):
    return [x for x in rows if x.success and x.two_pred is not None]


def _ret(rows):
    return [x for x in rows if x.success and x.gold_source is not None]


def _cal(rows):
    return [x for x in _lab(rows) if x.confidence is not None]


Stat = Callable[[Sequence[_Row]], float]

METRICS: Dict[str, Stat] = {
    # agreement on labels
    "qwk": lambda rs: M.qwk([x.gold for x in _lab(rs)], [x.label for x in _lab(rs)], N_LABELS),
    "accuracy": lambda rs: M.accuracy([x.gold for x in _lab(rs)], [x.label for x in _lab(rs)]),
    "macro_f1": lambda rs: M.macro_f1([x.gold for x in _lab(rs)], [x.label for x in _lab(rs)]),
    "adjacent_accuracy": lambda rs: M.adjacent_accuracy([x.gold for x in _lab(rs)],
                                                        [x.label for x in _lab(rs)]),
    "mae_label": lambda rs: M.mae([float(x.gold) for x in _lab(rs)],
                                  [float(x.label) for x in _lab(rs)]),
    # continuous agreement on the 0-1 scale
    "mae_score": lambda rs: M.mae([x.score / 100 for x in _ok(rs)], [x.gold01 for x in _ok(rs)]),
    "spearman": lambda rs: M.spearman([x.score for x in _ok(rs)], [x.gold01 for x in _ok(rs)]),
    # SciEntsBank 2-way
    "accuracy_2way": lambda rs: M.accuracy([x.two_gold for x in _two(rs)],
                                           [x.two_pred for x in _two(rs)]),
    "macro_f1_2way": lambda rs: M.macro_f1([x.two_gold for x in _two(rs)],
                                           [x.two_pred for x in _two(rs)]),
    # retrieval
    "hit_at_1": lambda rs: M.hit_at_k([x.ranked for x in _ret(rs)],
                                      [x.gold_source for x in _ret(rs)], 1),
    "hit_at_3": lambda rs: M.hit_at_k([x.ranked for x in _ret(rs)],
                                      [x.gold_source for x in _ret(rs)], 3),
    "mrr": lambda rs: M.mrr([x.ranked for x in _ret(rs)], [x.gold_source for x in _ret(rs)]),
    # calibration
    "auroc_error": lambda rs: M.auroc([1 if abs(x.label - x.gold) >= 1 else 0 for x in _cal(rs)],
                                      [1 - x.confidence for x in _cal(rs)]),
    "ece": lambda rs: M.ece([x.confidence for x in _cal(rs)],
                            [1 if x.label == x.gold else 0 for x in _cal(rs)]),
    # reliability (failure rates over every row; the rest over scored rows)
    "failure_rate": lambda rs: _mean([0.0 if x.success else 1.0 for x in rs]),
    "parse_failure_rate": lambda rs: _mean([1.0 if x.error_type == "parse_failure" else 0.0
                                            for x in rs]),
    "integrity_warning_rate": lambda rs: _mean([1.0 if x.warned else 0.0 for x in _ok(rs)]),
    "grounded_share": lambda rs: _ratio(sum(x.kept for x in _ok(rs)),
                                        sum(x.kept + x.dropped for x in _ok(rs))),
    "cited_share": lambda rs: _mean([1.0 if x.kept >= 1 else 0.0 for x in _ok(rs)]),
    # case study, in points out of 25
    "mae_points": lambda rs: _mean([abs(x.score / 4 - x.gold01 * 25) for x in _ok(rs)]),
}

AGREEMENT = ("qwk", "accuracy", "macro_f1", "adjacent_accuracy", "mae_label", "mae_score",
             "spearman")
TWO_WAY = ("accuracy_2way", "macro_f1_2way")
RETRIEVAL = ("hit_at_1", "hit_at_3", "mrr")
CALIBRATION = ("auroc_error", "ece")
RELIABILITY = ("failure_rate", "parse_failure_rate", "integrity_warning_rate",
               "grounded_share", "cited_share")
CONSISTENCY = ("consistency_score_std", "consistency_label_agreement")
INJECTION = ("injection_score_uplift", "injection_label_rise_share", "injection_detection_rate")
# Error-like metrics, where a decrease is an improvement (every ``mae_*`` metric too).
LOWER_IS_BETTER = frozenset({"ece", "failure_rate", "parse_failure_rate",
                             "consistency_score_std"})


def higher_is_better(metric: str) -> bool:
    """Direction of ``metric`` for comparison verdicts."""
    return not (metric.startswith("mae_") or metric in LOWER_IS_BETTER)


# --------------------------------------------------------------------------- thresholds

def fit_run_thresholds(results: Sequence[EvalResult],
                       datasets: Iterable[str]) -> FittedThresholds:
    """Fit per-dataset thresholds on this run's successful, non-variant dev results.

    The case study uses fixed point bands and is skipped. Datasets that cannot be fitted
    are left out and recorded in ``.errors`` with a fixed reason string.
    """
    fitted: Dict[str, Thresholds] = {}
    errors: Dict[str, str] = {}
    for ds in sorted(datasets):
        if ds == CASE_STUDY:
            continue
        dev = [r for r in results if r.dataset == ds and r.split == "dev" and _is_base(r)
               and r.repeat == 0 and r.success and r.score is not None]
        if not dev:
            errors[ds] = ERR_NO_DEV
            continue
        try:
            fitted[ds] = fit_thresholds([r.score for r in dev], [r.gold_label for r in dev],
                                        f"{ds}/dev")
        except ValueError:
            errors[ds] = ERR_CONSTANT
    return FittedThresholds(fitted, errors=errors)


def _rel_path(path: Path) -> str:
    p = Path(path).resolve()
    try:
        return p.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return p.name


def load_report_thresholds(report_json: Path) -> FittedThresholds:
    """Frozen thresholds from the ``thresholds`` section of a baseline report JSON.

    Variant runs (consistency, injection) cannot fit their own thresholds, so they reuse the
    same model's baseline thresholds (controller ruling R11). ``source`` is the report's
    repo-relative path (its file name when it lies outside the repo).
    """
    data = json.loads(Path(report_json).read_text(encoding="utf-8"))
    section = data.get("thresholds")
    if not isinstance(section, dict) or not section:
        raise ValueError("report JSON has no thresholds section")
    out: Dict[str, Thresholds] = {}
    for ds, th in sorted(section.items()):
        qwk_dev = th.get("qwk_dev")
        out[ds] = Thresholds(float(th["t1"]), float(th["t2"]), str(th["fitted_on"]),
                             NAN if qwk_dev is None else float(qwk_dev))
    return FittedThresholds(out, source=_rel_path(report_json))


# --------------------------------------------------------------------------- aggregate

def _boot(rows: Sequence[Any], cluster_of: Callable[[Any], str], stat: Callable,
          n_resamples: int) -> Estimate:
    return cluster_bootstrap(list(rows), cluster_of, stat, n_resamples=n_resamples, seed=SEED)


def _consistency_records(rows: Sequence[_Row], results: Sequence[EvalResult]):
    """Per item: (cluster, population std of repeat scores, all repeat labels equal?)."""
    by_item: Dict[str, List[_Row]] = {}
    for r, x in zip(results, rows):
        if x.success:
            by_item.setdefault(r.item_id, []).append(x)
    out = []
    for item in sorted(by_item):
        reps = by_item[item]
        if len(reps) < 2:
            continue
        labels = [x.label for x in reps]
        agree = None if any(lab is None for lab in labels) else float(len(set(labels)) == 1)
        out.append((reps[0].cluster, statistics.pstdev([x.score for x in reps]), agree))
    return out


def _injection_records(results: Sequence[EvalResult], ths: Dict[str, Thresholds]):
    """Per injected copy with a successful original: (dataset, split, cluster, uplift, rise,
    detected). The cluster is the original's question_id."""
    originals = {(r.item_id, r.repeat): r for r in results
                 if r.derived_from is None and r.variant is None}
    out = []
    for c in results:
        o = originals.get((c.derived_from, c.repeat)) if c.derived_from else None
        if o is None or not (o.success and c.success) or o.score is None or c.score is None:
            continue
        lo, lc = _label(o, ths), _label(c, ths)
        rise = None if lo is None or lc is None else float(lc > lo)
        detected = float(any(w.startswith(INJECTION_WARNING) for w in c.integrity_warnings))
        out.append((o.dataset, o.split, o.question_id, c.score - o.score, rise, detected))
    return out


def _est_dict(e: Estimate) -> Dict[str, Any]:
    return {"value": _num(e.value), "low": _num(e.low), "high": _num(e.high),
            "n_items": e.n_items, "n_clusters": e.n_clusters}


def aggregate(results: Sequence[EvalResult], cfg: ExperimentConfig,
              thresholds_by_dataset: Dict[str, Thresholds],
              n_resamples: int = N_RESAMPLES,
              thresholds_override: Optional[Dict[str, Thresholds]] = None) -> Aggregate:
    """Aggregate a run's results.

    ``thresholds_override`` (frozen baseline thresholds, see ``load_report_thresholds``)
    replaces the run's own thresholds for every dataset it covers.
    """
    ths = {ds: th for ds, th in thresholds_by_dataset.items()}
    override = dict(thresholds_override or {})
    ths.update(override)
    rows: List[MetricRow] = []
    counts: Dict[str, Dict[str, int]] = {}
    cluster = lambda x: x.cluster

    def add(ds: str, split: str, metric: str, est: Estimate) -> None:
        rows.append(MetricRow(ds, split, metric, est))

    for ds in sorted(cfg.datasets):
        counts[ds] = {}
        for split in cfg.datasets[ds]:
            in_split = [r for r in results if r.dataset == ds and r.split == split]
            base_res = [r for r in in_split if _is_base(r) and r.repeat == 0]
            base = [_to_row(r, ths) for r in base_res]
            counts[ds][split] = len(base)
            counts[ds][f"{split}_scored"] = len(_ok(base))
            counts[ds][f"{split}_failed"] = len(base) - len(_ok(base))
            counts[ds][f"{split}_variant_results"] = len(in_split) - len(base)

            names = list(AGREEMENT)
            if ds == "scientsbank":
                names += TWO_WAY
            if cfg.context_mode == "rag":
                names += RETRIEVAL
            names += CALIBRATION
            names += RELIABILITY
            scored = _ok(base)
            for name in names:
                # Failure rates are over every row; everything else over scored rows, so
                # its n_items counts scored rows only.
                rows_for = base if name in ("failure_rate", "parse_failure_rate") else scored
                add(ds, split, name, _boot(rows_for, cluster, METRICS[name], n_resamples))

            if ds == CASE_STUDY:
                add(ds, split, "mae_points", _boot(scored, cluster, METRICS["mae_points"],
                                                   n_resamples))
                qids = sorted({x.cluster for x in base})
                for k, qid in enumerate(qids, start=1):
                    q_rows = [x for x in scored if x.cluster == qid]
                    add(ds, split, f"mae_points_Q{k}",
                        _boot(q_rows, cluster, METRICS["mae_points"], n_resamples))
                counts[ds][f"{split}_questions"] = len(qids)

            if cfg.variant_set == "consistency":
                rep_res = [r for r in in_split if _is_base(r)]
                recs = _consistency_records([_to_row(r, ths) for r in rep_res], rep_res)
                add(ds, split, "consistency_score_std",
                    _boot(recs, lambda t: t[0], lambda s: _mean([t[1] for t in s]),
                          n_resamples))
                add(ds, split, "consistency_label_agreement",
                    _boot([t for t in recs if t[2] is not None], lambda t: t[0],
                          lambda s: _mean([t[2] for t in s]), n_resamples))

    if cfg.variant_set == "injection":
        recs = _injection_records(results, ths)
        for ds in sorted(cfg.datasets):
            for split in cfg.datasets[ds]:
                mine = [t for t in recs if t[0] == ds and t[1] == split]
                cl = lambda t: t[2]
                add(ds, split, "injection_score_uplift",
                    _boot(mine, cl, lambda s: _mean([t[3] for t in s]), n_resamples))
                add(ds, split, "injection_label_rise_share",
                    _boot([t for t in mine if t[4] is not None], cl,
                          lambda s: _mean([t[4] for t in s]), n_resamples))
                add(ds, split, "injection_detection_rate",
                    _boot(mine, cl, lambda s: _mean([t[5] for t in s]), n_resamples))

    failures = dict(sorted(Counter((r.error_type or "unknown")
                                   for r in results if not r.success).items()))
    providers = dict(sorted(Counter((r.provider or "unknown") for r in results).items()))
    extra: Dict[str, Any] = {
        "config": {"name": cfg.name, "phase": cfg.phase, "grader": cfg.grader,
                   "context_mode": cfg.context_mode, "variant_set": cfg.variant_set,
                   "repeats": cfg.repeats},
        "bootstrap": {"n_resamples": n_resamples, "seed": SEED, "cluster": "question_id",
                      "interval": "95% percentile"},
        "providers": providers,
        "threshold_errors": {ds: msg for ds, msg in
                             sorted(getattr(thresholds_by_dataset, "errors", {}).items())
                             if ds in cfg.datasets and ds not in override},
    }
    if thresholds_override is not None:
        extra["thresholds_source"] = getattr(thresholds_override, "source", None) or "override"
    for ds in sorted(cfg.datasets):
        if ds != CASE_STUDY and ds not in ths and ds not in extra["threshold_errors"]:
            extra["threshold_errors"][ds] = ERR_NO_DEV
    if len(providers) > 1:
        per: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for prov in providers:
            for ds in sorted(cfg.datasets):
                for split in cfg.datasets[ds]:
                    sel = [_to_row(r, ths) for r in results
                           if (r.provider or "unknown") == prov and r.dataset == ds
                           and r.split == split and _is_base(r) and r.repeat == 0
                           and r.success and r.score is not None]
                    if sel:
                        per.setdefault(prov, {}).setdefault(ds, {})[split] = _est_dict(
                            _boot(sel, cluster, METRICS["qwk"], n_resamples))
        extra["provider_qwk"] = per
    return Aggregate(rows=rows, counts=counts, failures=failures,
                     thresholds={ds: th for ds, th in ths.items() if ds in cfg.datasets},
                     extra=extra)


# --------------------------------------------------------------------------- loading

def load_run(run_dir: Path) -> Tuple[List[EvalResult], RunSummary]:
    run_dir = Path(run_dir)
    results = read_results(run_dir / RESULTS_FILE)
    hashes = {r.config_hash for r in results}
    if len(hashes) > 1:
        raise ValueError(f"{RESULTS_FILE} mixes {len(hashes)} config hashes")
    return results, read_summary(run_dir / SUMMARY_FILE)


# --------------------------------------------------------------------------- manifest

def _git() -> Tuple[Optional[str], Optional[bool]]:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=False, timeout=10)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                                capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None, None
    sha = head.stdout.strip() if head.returncode == 0 and head.stdout.strip() else None
    dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
    return sha, dirty


def _split_hash(sf: SplitFile) -> str:
    blob = json.dumps({"dataset": sf.dataset, "snapshot": sf.snapshot, "seed": sf.seed,
                       "splits": sf.splits, "banks": sf.banks},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _rel_config(path: Optional[Path]) -> Optional[str]:
    return None if path is None else _rel_path(path)


def build_manifest(cfg: ExperimentConfig, config_hash: str, summary: RunSummary,
                   split_files: Dict[str, SplitFile], snapshots: Dict[str, str], *,
                   embedding_model: Optional[str] = None,
                   thresholds: Optional[Dict[str, Thresholds]] = None,
                   config_file: Optional[Path] = None,
                   results: Optional[Sequence[EvalResult]] = None,
                   prompt_sha256: Optional[str] = None,
                   effective_settings: Optional[Dict[str, Any]] = None,
                   started_at: Optional[str] = None) -> RunManifest:
    """Spec 6.5 manifest. ``embedding_model`` comes from ``settings.embeddings`` (passed in).

    With ``results`` the call count and failures cover every recorded result (resumes
    included); otherwise they come from ``summary``. ``prompt_sha256``,
    ``effective_settings`` and ``started_at`` are the values recorded in ``run_meta.json``
    when the run started; without ``prompt_sha256`` the current template hash is used, and
    without ``started_at`` the last invocation's start.
    """
    from .. import __version__

    sha, dirty = _git()
    th_out: Dict[str, Any] = {ds: dataclasses.asdict(th)
                              for ds, th in sorted((thresholds or {}).items())}
    for ds, msg in sorted(getattr(thresholds, "errors", {}).items()):
        if ds not in th_out:
            th_out[ds] = {"error": msg}
    if results is not None:
        calls = len(results)
        failures = dict(sorted(Counter((r.error_type or "unknown")
                                       for r in results if not r.success).items()))
    else:
        calls = summary.graded + summary.skipped_existing
        failures = dict(summary.failures)
    seed = cfg.overrides.get("seed")
    fmt = cfg.overrides.get("response_format")
    return RunManifest(
        git_sha=sha, git_dirty=dirty, backend_version=__version__,
        prompt_template_sha256=prompt_sha256 or prompt_template_hash(),
        config_file=_rel_config(config_file),
        config_hash=config_hash, model=cfg.model, provider=cfg.provider,
        temperature=cfg.temperature, seed=seed if isinstance(seed, int) else None,
        response_format=fmt if isinstance(fmt, str) else None,
        embedding_model=embedding_model,
        effective_settings=dict(sorted((effective_settings or {}).items())),
        dataset_snapshots=dict(sorted(snapshots.items())),
        split_hashes={ds: _split_hash(sf) for ds, sf in sorted(split_files.items())},
        item_counts={ds: dict(sf.counts) for ds, sf in sorted(split_files.items())},
        thresholds=th_out, thresholds_source=getattr(thresholds, "source", None),
        started_at=started_at or summary.started_at, finished_at=summary.finished_at,
        calls=calls, prompt_tokens=summary.tokens_in, completion_tokens=summary.tokens_out,
        estimated_cost_usd=summary.cost_usd, failures=failures,
    )


# --------------------------------------------------------------------------- rendering

def _num(x: Any) -> Any:
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return _num(obj)


def render_json(agg: Aggregate, manifest: RunManifest) -> dict:
    metrics: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in agg.rows:
        metrics.setdefault(row.dataset, {}).setdefault(row.split, {})[row.metric] = \
            _est_dict(row.estimate)
    return {
        "manifest": _clean(manifest.to_dict()),
        "metrics": metrics,
        "counts": _clean(agg.counts),
        "failures": _clean(agg.failures),
        "thresholds": {ds: _clean(dataclasses.asdict(th))
                       for ds, th in sorted(agg.thresholds.items())},
        "extra": _clean(agg.extra),
    }


def _f(x: Any) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    if isinstance(x, float):
        return f"{x:.3f}"
    return str(x)


def _ci(e: Estimate) -> str:
    if math.isnan(e.value):
        return "n/a"
    return f"{_f(e.value)} [{_f(e.low)}, {_f(e.high)}]"


def _cell(v: Any) -> str:
    if isinstance(v, (dict, list)):
        text = json.dumps(_clean(v), sort_keys=True, ensure_ascii=False) if v else "n/a"
    else:
        text = _f(v)
    return text.replace("|", "\\|")


def _table(header: Sequence[str], body: Sequence[Sequence[str]]) -> List[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return lines + [""]


class _Lookup:
    def __init__(self, rows: Sequence[MetricRow]):
        self.by = {(r.dataset, r.split, r.metric): r.estimate for r in rows}
        self.keys: List[Tuple[str, str]] = []
        for r in rows:
            if (r.dataset, r.split) not in self.keys:
                self.keys.append((r.dataset, r.split))

    def having(self, names: Sequence[str], exclude: Sequence[str] = ()) -> List[Tuple[str, str]]:
        return [k for k in self.keys if k[0] not in exclude
                and any((k[0], k[1], m) in self.by for m in names)]

    def table(self, names: Sequence[str], exclude: Sequence[str] = ()) -> List[str]:
        keys = self.having(names, exclude)
        if not keys:
            return ["Not applicable to this run.", ""]
        body = []
        for ds, split in keys:
            ests = [self.by.get((ds, split, m)) for m in names]
            n = max((e.n_items for e in ests if e is not None), default=0)
            body.append([ds, split] + [_ci(e) if e is not None else "n/a" for e in ests]
                        + [str(n)])
        return _table(["Dataset", "Split"] + list(names) + ["n"], body)


def render_markdown(agg: Aggregate, manifest: RunManifest) -> str:
    look = _Lookup(agg.rows)
    conf = agg.extra.get("config", {})
    title = conf.get("name") or manifest.config_hash or "run"
    phase = conf.get("phase")
    out: List[str] = [f"# Evaluation report: {title}" + (f" (phase {phase})" if phase else ""),
                      ""]
    boot = agg.extra.get("bootstrap", {})
    if boot:
        out += [f"Intervals are {boot.get('interval')} intervals from "
                f"{boot.get('n_resamples')} cluster-bootstrap resamples over "
                f"{boot.get('cluster')} (seed {boot.get('seed')}). Values read "
                "`value [low, high]`; `n/a` means undefined.", ""]

    out += ["## Manifest", ""]
    out += _table(["Field", "Value"],
                  [[k, _cell(v)] for k, v in manifest.to_dict().items()])

    out += ["## Data and cleaning counts", ""]
    if manifest.item_counts:
        out += ["Items after cleaning (split files):", ""]
        out += _table(["Dataset", "Split", "Items"],
                      [[ds, s, _f(n)] for ds, c in sorted(manifest.item_counts.items())
                       for s, n in sorted(c.items())])
    if agg.counts:
        out += ["Results in this run:", ""]
        body = []
        for ds, c in agg.counts.items():
            for s, n in c.items():
                if f"{s}_scored" in c:
                    body.append([ds, s, str(n), str(c[f"{s}_scored"]),
                                 str(c.get(f"{s}_failed", 0)),
                                 str(c.get(f"{s}_variant_results", 0))])
        out += _table(["Dataset", "Split", "Results", "Scored", "Failed", "Variant results"],
                      body)

    out += ["## Thresholds", ""]
    if agg.extra.get("thresholds_source"):
        out += [f"Frozen thresholds loaded from `{agg.extra['thresholds_source']}` "
                "(baseline report); not fitted on this run.", ""]
    if agg.thresholds:
        out += _table(["Dataset", "t1", "t2", "Fitted on", "Dev QWK"],
                      [[ds, _f(th.t1), _f(th.t2), th.fitted_on, _f(th.qwk_dev)]
                       for ds, th in sorted(agg.thresholds.items())])
    for ds, msg in sorted(agg.extra.get("threshold_errors", {}).items()):
        out.append(f"- {ds}: thresholds could not be fitted ({msg}); its label metrics are n/a.")
    if any(k[0] == CASE_STUDY for k in look.keys):
        out.append(f"- {CASE_STUDY}: fixed case-study bands (0-8, 9-17 and 18-25 points), "
                   "not fitted.")
    out.append("")

    injection = conf.get("variant_set") == "injection"
    # Injection runs grade clean originals plus injected copies; their agreement and
    # calibration describe that mix, not the configuration, so only the JSON keeps them.
    suppressed = ["Not reported for injection runs: the baseline report of the same "
                  "configuration gives these metrics.", ""]
    out += ["## Agreement", ""]
    out += suppressed if injection else look.table(AGREEMENT, exclude=(CASE_STUDY,))
    providers = agg.extra.get("providers", {})
    if len(providers) > 1 and not injection:
        out += ["> **Warning:** More than one provider served this run (spec section 9); "
                "provider routing may change model behaviour. Per-provider QWK:", ""]
        body = []
        for prov, by_ds in sorted(agg.extra.get("provider_qwk", {}).items()):
            for ds, by_split in sorted(by_ds.items()):
                for s, e in by_split.items():
                    cell = ("n/a" if e["value"] is None else
                            f"{_f(e['value'])} [{_f(e['low'])}, {_f(e['high'])}]")
                    body.append([prov, ds, s, cell, str(e["n_items"])])
        out += _table(["Provider", "Dataset", "Split", "qwk", "n"], body)

    out += ["## SciEntsBank 2-way", ""]
    out += look.table(TWO_WAY)
    out += ["## Retrieval", ""]
    out += look.table(RETRIEVAL, exclude=(CASE_STUDY,))
    out += ["## Calibration", "",
            "Error is |label - gold| >= 1; auroc_error is the AUROC of (1 - confidence) for "
            "predicting error; ece uses 10 bins.", ""]
    out += suppressed if injection else look.table(CALIBRATION, exclude=(CASE_STUDY,))
    out += ["## Reliability", ""]
    out += look.table(RELIABILITY, exclude=(CASE_STUDY,))
    out += ["Failures by type: " + (", ".join(f"{k}: {v}" for k, v in agg.failures.items())
                                    if agg.failures else "none"),
            "", "Served providers: " + (", ".join(f"{k}: {v}" for k, v in providers.items())
                                        if providers else "n/a"), ""]

    out += ["## Case study", ""]
    case_keys = [k for k in look.keys if k[0] == CASE_STUDY]
    if not case_keys:
        out += ["Not part of this run.", ""]
    for ds, split in case_keys:
        out += ["Reported qualitatively, without statistical claims: values only, no "
                "intervals. Questions are labelled by sorted question id.", ""]
        qs = sorted((m for (d, s, m) in look.by if d == ds and s == split
                     and m.startswith("mae_points_Q")), key=lambda m: int(m.rsplit("Q", 1)[1]))
        body = [[m.rsplit("_", 1)[1], str(look.by[(ds, split, m)].n_items),
                 _f(look.by[(ds, split, m)].value)] for m in qs]
        overall = look.by.get((ds, split, "mae_points"))
        if overall is not None:
            body.append(["All", str(overall.n_items), _f(overall.value)])
        out += _table(["Question", "Answers", "MAE (points of 25)"], body)
        vals = [f"{m}: {_f(look.by[(ds, split, m)].value)}" for m in
                ("accuracy", "adjacent_accuracy", "qwk", "mae_score")
                if (ds, split, m) in look.by]
        out += ["Label agreement (fixed bands): " + ", ".join(vals), ""]

    out += ["## Variants", ""]
    variant_set = conf.get("variant_set")
    if look.having(CONSISTENCY):
        out += ["### Consistency", "",
                "Mean per-item score standard deviation over repeats (0-100 points) and the "
                "share of items whose repeats all get the same label.", ""]
        out += look.table(CONSISTENCY)
    if look.having(INJECTION):
        out += ["### Injection", "",
                "Mean score uplift of the injected copy over its clean original (0-100 "
                "points), the share whose label rises, and the share flagged with a "
                f"`{INJECTION_WARNING}` integrity warning.", ""]
        out += look.table(INJECTION)
        if not agg.extra.get("thresholds_source"):
            out += ["Note: injection_label_rise_share needs frozen baseline thresholds; run "
                    "`report --thresholds-from <baseline .json>`.", ""]
    if not look.having(CONSISTENCY) and not look.having(INJECTION):
        out += [("No variant set in this run." if not variant_set
                 else "No variant results in this run."), ""]

    out += ["## Limitations", ""] + [f"- {t}" for t in LIMITATIONS] + [""]
    out += ["## Citations", ""] + [f"- {t}" for t in CITATIONS] + [""]
    return "\n".join(out)


def write_report(agg: Aggregate, manifest: RunManifest, out_base: Path) -> Tuple[Path, Path]:
    """Write ``<out_base>.md`` and ``<out_base>.json`` (suffixes appended, never replaced)."""
    out_base = Path(out_base)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    md_path = out_base.with_name(out_base.name + ".md")
    json_path = out_base.with_name(out_base.name + ".json")
    md_path.write_text(render_markdown(agg, manifest), encoding="utf-8")
    json_path.write_text(json.dumps(render_json(agg, manifest), indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n", encoding="utf-8")
    return md_path, json_path


# --------------------------------------------------------------------------- comparison

def _compare_index(results: Sequence[EvalResult], ths: Dict[str, Thresholds]):
    return {(r.dataset, r.split, r.item_id, r.repeat): _to_row(r, ths)
            for r in results if r.derived_from is None}


def compare_runs(a: Sequence[EvalResult], b: Sequence[EvalResult],
                 thresholds_a: Dict[str, Thresholds], thresholds_b: Dict[str, Thresholds],
                 metrics: Sequence[str] = ("qwk", "mae_score", "spearman"),
                 n_resamples: int = N_RESAMPLES
                 ) -> List[Tuple[str, str, str, Estimate, str]]:
    """Paired B - A differences on items scored in both runs, keyed by (item_id, repeat).

    Each side is labelled with its own thresholds. The verdict is ``describe_difference``
    in the metric's direction (``higher_is_better``), which is ``"undefined"`` when the
    estimate or its interval is nan. The case study gets no statistical claims (spec 4.4):
    its rows carry the point difference only (nan interval) and ``CASE_STUDY_VERDICT``.
    """
    ia, ib = _compare_index(a, thresholds_a), _compare_index(b, thresholds_b)
    common = sorted(k for k in set(ia) & set(ib) if ia[k].success and ib[k].success)
    groups: Dict[Tuple[str, str], List[Tuple[str, str, str, int]]] = {}
    for k in common:
        groups.setdefault((k[0], k[1]), []).append(k)
    out = []
    for (ds, split) in sorted(groups):
        keys = groups[(ds, split)]
        ra, rb = [ia[k] for k in keys], [ib[k] for k in keys]
        case = ds == CASE_STUDY
        for m in metrics:
            est = paired_difference(ra, rb, lambda x: x.key, lambda x: x.cluster, METRICS[m],
                                    n_resamples=0 if case else n_resamples, seed=SEED)
            verdict = (CASE_STUDY_VERDICT if case
                       else describe_difference(est, higher_is_better(m)))
            out.append((ds, split, m, est, verdict))
    return out


def compare_counts(a: Sequence[EvalResult], b: Sequence[EvalResult]
                   ) -> Dict[Tuple[str, str], Dict[str, int]]:
    """Per (dataset, split): results and failures on each side, paired items, pairs dropped
    because a side failed, and items present on one side only (non-variant results)."""
    def index(results):
        return {(r.dataset, r.split, r.item_id, r.repeat): r for r in results
                if r.derived_from is None}

    ia, ib = index(a), index(b)
    out: Dict[Tuple[str, str], Dict[str, int]] = {}
    for key in sorted(set(ia) | set(ib)):
        c = out.setdefault((key[0], key[1]), {
            "a_results": 0, "a_failures": 0, "b_results": 0, "b_failures": 0,
            "paired": 0, "pairs_dropped": 0, "unmatched": 0})
        ra, rb = ia.get(key), ib.get(key)
        ok_a = ra is not None and ra.success and ra.score is not None
        ok_b = rb is not None and rb.success and rb.score is not None
        if ra is not None:
            c["a_results"] += 1
            c["a_failures"] += 0 if ok_a else 1
        if rb is not None:
            c["b_results"] += 1
            c["b_failures"] += 0 if ok_b else 1
        if ra is None or rb is None:
            c["unmatched"] += 1
        elif ok_a and ok_b:
            c["paired"] += 1
        else:
            c["pairs_dropped"] += 1
    return out


def render_comparison(rows: Sequence[Tuple[str, str, str, Estimate, str]],
                      counts: Optional[Dict[Tuple[str, str], Dict[str, int]]] = None) -> str:
    """Markdown table for ``compare_runs`` output; undefined rows read ``n/a (undefined)``.

    Case-study rows show the point difference without an interval. With ``counts``
    (``compare_counts``) a second table lists failures per side and dropped pairs.
    """
    body = []
    for ds, split, m, est, verdict in rows:
        if verdict == CASE_STUDY_VERDICT:
            body.append([ds, split, m, _f(est.value), verdict, str(est.n_items)])
        elif verdict == "undefined" or any(math.isnan(x) for x in (est.value, est.low, est.high)):
            body.append([ds, split, m, "n/a (undefined)", "n/a (undefined)", str(est.n_items)])
        else:
            body.append([ds, split, m, _ci(est), verdict, str(est.n_items)])
    out = _table(["Dataset", "Split", "Metric", "Difference (B - A) [95% CI]",
                  "Verdict", "Paired items"], body)
    if counts:
        keys = ("a_results", "a_failures", "b_results", "b_failures", "paired",
                "pairs_dropped", "unmatched")
        out += ["Items per side (pairs are dropped when either side failed):", ""]
        out += _table(["Dataset", "Split", "A results", "A failures", "B results",
                       "B failures", "Paired", "Pairs dropped", "Unmatched"],
                      [[ds, split] + [str(c[k]) for k in keys]
                       for (ds, split), c in sorted(counts.items())])
    return "\n".join(out)
