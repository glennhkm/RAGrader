"""Resumable experiment runner: concurrency, checkpointing, backoff and a cost cap.

``plan_run`` turns a config and the prepared items into a ``RunPlan``; ``run``
grades the plan's (item, repeat) pairs, appending each result to
``out_dir/results.jsonl`` as soon as it completes, and writes
``out_dir/run_summary.json``. Re-running the same plan skips pairs already on
disk, so an interrupted run resumes where it stopped.
"""

import dataclasses
import json
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

from loguru import logger

from .adversarial import derive_consistency, derive_injection, load_templates
from .experiment import ExperimentConfig, config_hash
from .graders.base import Grader, GradeRequest, RawGrade, TransientGraderError
from .graders.http import http_namespace
from .materials import MaterialDoc, build_materials, gold_source
from .privacy import assert_output_allowed
from .schema import EvalItem, EvalResult, append_jsonl, read_results
from .splits import snapshot_hash

EST_PROMPT_TOKENS = 2000
EST_COMPLETION_TOKENS = 300
CONSISTENCY_N = 100
INJECTION_N_PER_SPLIT = 100
RESULTS_FILE = "results.jsonl"
SUMMARY_FILE = "run_summary.json"


class BudgetError(RuntimeError):
    """The estimated cost of a run exceeds the configured ``max_cost_usd``."""


@dataclass
class RunPlan:
    config: ExperimentConfig
    config_hash: str
    items: List[EvalItem]
    out_dir: Path
    estimated_cost_usd: float
    # Materials per dataset, built from ALL of that dataset's items (every split and role).
    materials: Dict[str, List[MaterialDoc]] = field(default_factory=dict)

    def pairs(self) -> List[Tuple[EvalItem, int]]:
        """The plan's work units: every item expanded into repeats 0..repeats-1."""
        return [(item, r) for item in self.items for r in range(self.config.repeats)]


@dataclass
class RunSummary:
    """Outcome of one ``run`` invocation.

    ``cost_usd``, ``tokens_in`` and ``tokens_out`` are cumulative over every record
    in ``results.jsonl`` for this config hash (earlier, resumed invocations included);
    ``cost_usd_this_run`` covers only this invocation. ``graded`` and ``failures``
    count only the results recorded by this invocation.
    """

    out_dir: Path
    graded: int
    skipped_existing: int
    failures: Dict[str, int]
    cost_usd: float
    tokens_in: int
    tokens_out: int
    aborted: Optional[str]
    started_at: str
    finished_at: str
    cost_usd_this_run: float = 0.0


def _cost(cfg: ExperimentConfig, prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * cfg.price_in_per_mtok
            + completion_tokens * cfg.price_out_per_mtok) / 1e6


def plan_run(cfg: ExperimentConfig, items_by_dataset: Dict[str, List[EvalItem]],
             out_root: Path, reference_dir: Optional[Path] = None) -> RunPlan:
    """``reference_dir`` holds the reference documents named by the items (case study)."""
    missing = [ds for ds in cfg.datasets if ds not in items_by_dataset]
    if missing:
        raise ValueError(f"no items supplied for datasets: {sorted(missing)}")
    snapshots = {ds: snapshot_hash(items_by_dataset[ds]) for ds in sorted(cfg.datasets)}
    h = config_hash(cfg, snapshots)
    out_dir = Path(out_root) / f"{cfg.name}-{h}"

    assert_output_allowed(cfg.datasets, out_dir)

    selected: List[EvalItem] = []
    limit = cfg.max_items_per_split
    for ds in sorted(cfg.datasets):
        for split in sorted(set(cfg.datasets[ds])):
            chosen = sorted((i for i in items_by_dataset[ds]
                             if i.role == "eval" and i.split == split),
                            key=lambda i: i.item_id)
            selected.extend(chosen if limit is None else chosen[:limit])
    if cfg.variant_set == "consistency":
        selected = derive_consistency(selected, n=CONSISTENCY_N)
    elif cfg.variant_set == "injection":
        selected = derive_injection(selected, load_templates(),
                                    n_per_split=INJECTION_N_PER_SPLIT)

    materials = {ds: build_materials(items_by_dataset[ds], reference_dir)
                 for ds in sorted(cfg.datasets)}
    n_calls = len(selected) * cfg.repeats
    estimate = n_calls * _cost(cfg, EST_PROMPT_TOKENS, EST_COMPLETION_TOKENS)
    return RunPlan(cfg, h, selected, out_dir, estimate, materials)


def _repair_trailing_line(path: Path) -> None:
    """Make ``path`` end with a newline so appends never glue onto a partial record.

    A last line without ``\\n`` is kept (newline added) when it is complete JSON,
    and truncated otherwise; every complete line is preserved.
    """
    if not path.exists():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    cut = data.rfind(b"\n") + 1
    tail = data[cut:]
    try:
        json.loads(tail.decode("utf-8"))
        complete = True
    except (UnicodeDecodeError, json.JSONDecodeError):
        complete = False
    with open(path, "r+b") as fh:
        if complete:
            fh.seek(0, os.SEEK_END)
            fh.write(b"\n")
        else:
            logger.warning("Truncating partial trailing line in {}", path.name)
            fh.truncate(cut)
        fh.flush()
        os.fsync(fh.fileno())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_result(plan: RunPlan, item: EvalItem, repeat: int, raw: RawGrade,
               latency: float) -> EvalResult:
    return EvalResult(
        item_id=item.item_id, config_hash=plan.config_hash, dataset=item.dataset,
        question_id=item.question_id, split=item.split, gold_label=item.gold_label,
        success=raw.success, score=raw.score, confidence=raw.confidence,
        error_type=raw.error_type, integrity_warnings=tuple(raw.integrity_warnings),
        citations_kept=raw.citations_kept, citations_dropped=raw.citations_dropped,
        retrieved_sources=tuple(raw.retrieved_sources), gold_source=gold_source(item),
        provider=raw.provider, prompt_tokens=raw.prompt_tokens,
        completion_tokens=raw.completion_tokens, tokens_estimated=raw.tokens_estimated,
        latency_s=latency, repeat=repeat, variant=item.variant,
        derived_from=item.derived_from, gold_score=item.gold_score,
        gold_label_raw=item.gold_label_raw, feedback=raw.feedback,
    )


def _provider_error(plan: RunPlan, item: EvalItem, repeat: int, latency: float) -> EvalResult:
    return EvalResult(
        item_id=item.item_id, config_hash=plan.config_hash, dataset=item.dataset,
        question_id=item.question_id, split=item.split, gold_label=item.gold_label,
        success=False, score=None, confidence=None, error_type="provider_error",
        gold_source=gold_source(item), latency_s=latency, repeat=repeat,
        variant=item.variant, derived_from=item.derived_from, gold_score=item.gold_score,
        gold_label_raw=item.gold_label_raw, feedback="",
    )


def _write_summary(summary: RunSummary) -> None:
    body = dataclasses.asdict(summary)
    body["out_dir"] = str(summary.out_dir)
    path = Path(summary.out_dir) / SUMMARY_FILE
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def read_summary(path: Path) -> RunSummary:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["out_dir"] = Path(data["out_dir"])
    return RunSummary(**data)


def run(plan: RunPlan, grader: Grader, *, clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep, max_attempts: int = 5) -> RunSummary:
    cfg = plan.config
    assert_output_allowed(set(cfg.datasets) | {i.dataset for i in plan.items}, plan.out_dir)
    if plan.estimated_cost_usd > cfg.max_cost_usd:
        raise BudgetError(
            f"estimated cost ${plan.estimated_cost_usd:.4f} exceeds max_cost_usd "
            f"${cfg.max_cost_usd:.4f}")
    started_at = _now()
    out_dir = Path(plan.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / RESULTS_FILE

    existing: List[EvalResult] = []
    if results_path.exists():
        # Check ownership before touching the file: read_results tolerates a partial last line.
        existing = read_results(results_path)
        if any(r.config_hash != plan.config_hash for r in existing):
            raise ValueError("results.jsonl belongs to another configuration")
        _repair_trailing_line(results_path)
    done: Set[Tuple[str, int]] = {(r.item_id, r.repeat) for r in existing}
    prior_cost = sum(_cost(cfg, r.prompt_tokens, r.completion_tokens) for r in existing)
    prior_in = sum(r.prompt_tokens for r in existing)
    prior_out = sum(r.completion_tokens for r in existing)

    all_pairs = plan.pairs()
    pending = [(i, r) for i, r in all_pairs if (i.item_id, r) not in done]
    skipped = len(all_pairs) - len(pending)

    lock = threading.Lock()
    stop = threading.Event()
    # The running cap is cumulative across resumes: seed it with what is already on disk.
    state = {"graded": 0, "cost": prior_cost, "tin": prior_in, "tout": prior_out}
    if prior_cost > cfg.max_cost_usd:
        stop.set()

    workdir = out_dir / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    namespaces = {ds: http_namespace(plan.config_hash, ds) for ds in sorted(cfg.datasets)}
    if not stop.is_set():
        for ds in sorted({i.dataset for i, _ in pending}):
            grader.prepare_namespace(namespaces[ds], plan.materials.get(ds, []), workdir)
    failures: Dict[str, int] = {}

    def record(result: EvalResult) -> None:
        with lock:
            append_jsonl(results_path, result)
            state["graded"] += 1
            state["tin"] += result.prompt_tokens
            state["tout"] += result.completion_tokens
            state["cost"] += _cost(cfg, result.prompt_tokens, result.completion_tokens)
            if not result.success:
                key = result.error_type or "unknown"
                failures[key] = failures.get(key, 0) + 1
            if state["cost"] > cfg.max_cost_usd:
                stop.set()

    def grade_one(item: EvalItem, repeat: int) -> None:
        if stop.is_set():
            return  # budget_abort: not recorded, so a later run grades it
        request = GradeRequest(question=item.question, answer=item.answer,
                               language=item.language)
        namespace = namespaces[item.dataset]
        attempt = 1
        while True:
            t0 = clock()
            try:
                raw = grader.grade(namespace, item, request)
            except TransientGraderError as exc:
                latency = clock() - t0
                if attempt >= max_attempts:
                    logger.warning("Grading {} gave up after {} transient failures",
                                   item.item_id, attempt)
                    record(_provider_error(plan, item, repeat, latency))
                    return
                if stop.is_set():
                    return  # budget_abort during backoff: not recorded
                base = exc.retry_after if exc.retry_after is not None else 2 ** attempt
                sleep(min(60, base))
                if stop.is_set():
                    return
                attempt += 1
                continue
            except Exception as exc:  # non-transient: record, never log the submission text
                latency = clock() - t0
                logger.warning("Grading {} failed: {}", item.item_id, type(exc).__name__)
                record(_provider_error(plan, item, repeat, latency))
                return
            record(_to_result(plan, item, repeat, raw, clock() - t0))
            return

    limit = max(1, cfg.concurrency) * 2
    queue: Iterator[Tuple[EvalItem, int]] = iter(pending)
    in_flight: Set[Future] = set()
    executor = ThreadPoolExecutor(max_workers=max(1, cfg.concurrency))
    try:
        exhausted = False
        while True:
            while not exhausted and not stop.is_set() and len(in_flight) < limit:
                nxt = next(queue, None)
                if nxt is None:
                    exhausted = True
                    break
                in_flight.add(executor.submit(grade_one, *nxt))
            if not in_flight:
                break
            finished, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in finished:
                fut.result()  # re-raise BaseException (e.g. KeyboardInterrupt) from a worker
    except BaseException:
        stop.set()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    executor.shutdown(wait=True)

    summary = RunSummary(
        out_dir=out_dir, graded=state["graded"], skipped_existing=skipped,
        failures=dict(sorted(failures.items())), cost_usd=state["cost"],
        cost_usd_this_run=state["cost"] - prior_cost,
        tokens_in=state["tin"], tokens_out=state["tout"],
        aborted="budget" if stop.is_set() and state["graded"] < len(pending) else None,
        started_at=started_at, finished_at=_now(),
    )
    _write_summary(summary)
    return summary
