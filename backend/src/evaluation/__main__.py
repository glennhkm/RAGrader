"""Evaluation CLI: ``python -m src.evaluation prepare|run|report|compare|smoke``.

- ``prepare`` loads a dataset, splits it and freezes the split file.
- ``run`` grades a configuration's items and checkpoints per-item results.
- ``report`` aggregates a run into Markdown + JSON (aggregates only).
- ``compare`` reports paired differences between two runs.
- ``smoke`` is the CI plumbing check (stub grader, synthetic set).

Per-item text is never printed, except by the hidden ``canaries`` helper, whose only job is
to print answer snippets of the prepared private items for a ``grep -F -f`` privacy check.
Graders are built lazily through ``build_grader``, so ``smoke`` never imports Chroma.
"""

import argparse
import dataclasses
import hashlib
import json
import math
import os
import random
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .datasets import load_dataset
from .datasets.jk_case import DEFAULT_REFERENCE_NAME, load_jk_case
from .experiment import ExperimentConfig, config_hash, load_experiment
from .graders import build_grader
from .paths import EVAL_ASSETS, PRIVATE_DIR, REPORTS_DIR
from .privacy import PrivacyError, assert_output_allowed
from .report import (
    FittedThresholds,
    aggregate,
    build_manifest,
    compare_counts,
    compare_runs,
    fit_run_thresholds,
    load_report_thresholds,
    load_run,
    render_comparison,
    render_json,
    write_report,
)
from .runner import BudgetError, RunPlan, plan_run, run
from .schema import DATASETS, EvalItem, EvalResult, is_private, read_items, write_jsonl
from .splits import DEFAULT_SEED, SplitFile, prepare_dataset, read_split_file, \
    snapshot_hash, write_split_file
from .thresholds import fit_thresholds

# Path constants (module level so tests can redirect them).
PREPARED_DIR = PRIVATE_DIR / "evaluation" / "prepared"
PRIVATE_SPLITS_DIR = PRIVATE_DIR / "evaluation" / "splits"
PUBLIC_SPLITS_DIR = EVAL_ASSETS / "splits"
CHECKSUMS_FILE = PUBLIC_SPLITS_DIR / "private_checksums.json"
DEFAULT_RUNS_ROOT = PRIVATE_DIR / "evaluation" / "runs"
SMOKE_CONFIG = EVAL_ASSETS / "experiments" / "smoke-stub.yaml"
DEFAULT_SOURCES: Dict[str, Path] = {
    "engsaf": PRIVATE_DIR / "datasets" / "engsaf" / "engsaf_train.csv",
    "jk_case": PRIVATE_DIR / "datasets" / "jk-usk" / "jaringan_komputer_usk.csv",
    "scientsbank": PRIVATE_DIR / "cache" / "scientsbank",
}
RUN_META_FILE = "run_meta.json"
FROZEN_MSG = "split file is frozen; snapshot changed"
SMOKE_RESAMPLES = 200
SMOKE_LABEL = ("smoke thresholds are fitted on the smoke split itself: a CI plumbing check, "
               "not an evaluation")
CANARY_COUNT = 50
CANARY_WORDS = 8
CANARY_DATASETS = ("engsaf", "jk_case")


class CliError(Exception):
    """A user-facing failure: one line on stderr, exit code 2."""


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- prepare

def _load_source(name: str, source: Optional[Path],
                 reference_pdf: Optional[Path]) -> Tuple[List[EvalItem], dict]:
    if name == "synthetic":
        return load_dataset("synthetic", source)
    path = Path(source) if source is not None else DEFAULT_SOURCES[name]
    if not path.exists() and name != "scientsbank":
        raise CliError(f"source not found: {path}")
    if name == "jk_case":
        pdf = Path(reference_pdf) if reference_pdf else path.parent / DEFAULT_REFERENCE_NAME
        if not pdf.exists():
            raise CliError(f"reference PDF not found: {pdf}")
        return _guarded(name, lambda: load_jk_case(path, pdf))
    return _guarded(name, lambda: load_dataset(name, path))


def _guarded(name: str, load):
    """Run a loader; its error messages may quote source rows, so only the type is shown."""
    try:
        return load()
    except (KeyError, ValueError) as exc:
        raise CliError(f"could not load {name}: {type(exc).__name__} while reading the source")


def _split_target(name: str) -> Optional[Path]:
    if name == "synthetic":
        return None
    if is_private(name):
        return PRIVATE_SPLITS_DIR / f"{name}.json"
    return PUBLIC_SPLITS_DIR / f"{name}.json"


def _read_checksums() -> Dict[str, str]:
    if not CHECKSUMS_FILE.exists():
        return {}
    return json.loads(CHECKSUMS_FILE.read_text(encoding="utf-8"))


def _summary_numbers(report: dict) -> Dict[str, Any]:
    """Only numeric source statistics (never strings, which could carry item text)."""
    out: Dict[str, Any] = {}
    for k, v in sorted(report.items()):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
        elif isinstance(v, dict) and v and all(isinstance(x, int) for x in v.values()):
            out[k] = dict(sorted(v.items()))
    return out


def _prepare(name: str, source: Optional[Path], reference_pdf: Optional[Path],
             out: Optional[Path], refreeze: bool) -> Tuple[Path, SplitFile]:
    if out is not None:
        out_dir = Path(out)
    elif name == "synthetic":
        out_dir = Path(tempfile.mkdtemp(prefix="eval-synthetic-"))
    else:
        out_dir = PREPARED_DIR
    assert_output_allowed([name], out_dir)

    raw_items, source_report = _load_source(name, source, reference_pdf)
    items, split_file = prepare_dataset(name, raw_items)

    target = _split_target(name)
    staged: Optional[Path] = None
    if target is not None:
        hashed = is_private(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".json", dir=target.parent)
        os.close(fd)
        staged = Path(tmp)
        write_split_file(staged, split_file, hash_ids=hashed)
        try:
            changed = target.exists() and read_split_file(target).snapshot != split_file.snapshot
            if hashed:
                recorded = _read_checksums().get(name)
                digest = hashlib.sha256(staged.read_bytes()).hexdigest()
                changed = changed or (recorded is not None and recorded != digest)
            if changed and not refreeze:
                raise CliError(f"{FROZEN_MSG} ({name}); pass --refreeze to replace it")
        except BaseException:
            staged.unlink(missing_ok=True)
            raise

    prepared = out_dir / f"{name}.jsonl"
    write_jsonl(prepared, items)
    if staged is not None:
        os.replace(staged, target)
        if is_private(name):
            sums = _read_checksums()
            sums[name] = hashlib.sha256(target.read_bytes()).hexdigest()
            CHECKSUMS_FILE.parent.mkdir(parents=True, exist_ok=True)
            CHECKSUMS_FILE.write_text(json.dumps(dict(sorted(sums.items())), indent=2) + "\n",
                                      encoding="utf-8")

    print(f"{name}: {len(items)} prepared items, snapshot {split_file.snapshot[:16]}")
    for key, n in sorted(split_file.counts.items()):
        print(f"  {key}: {n}")
    numbers = _summary_numbers(source_report)
    if numbers:
        print(f"  source: {json.dumps(numbers, sort_keys=True)}")
    print(f"  prepared items: {prepared}")
    if target is not None:
        print(f"  split file: {target}")
    return prepared, split_file


def cmd_prepare(args: argparse.Namespace) -> int:
    if args.reference_pdf and args.dataset != "jk_case":
        raise CliError("--reference-pdf applies only to --dataset jk_case")
    _prepare(args.dataset, args.source, args.reference_pdf, args.out, args.refreeze)
    return 0


# --------------------------------------------------------------------------- run

def _load_prepared(cfg: ExperimentConfig) -> Tuple[Dict[str, List[EvalItem]], Dict[str, SplitFile]]:
    items_by_dataset: Dict[str, List[EvalItem]] = {}
    split_files: Dict[str, SplitFile] = {}
    for ds in sorted(cfg.datasets):
        if ds == "synthetic":
            raw, _ = load_dataset("synthetic", None)
            items, sf = prepare_dataset("synthetic", raw)
        else:
            prepared = PREPARED_DIR / f"{ds}.jsonl"
            target = _split_target(ds)
            if not prepared.exists() or target is None or not target.exists():
                raise CliError(f"no prepared items for {ds}: run `prepare --dataset {ds}` first")
            items = read_items(prepared)
            sf = read_split_file(target)
            if snapshot_hash(items) != sf.snapshot:
                raise CliError(f"prepared items for {ds} do not match the frozen split file; "
                               f"run `prepare --dataset {ds}` again")
        items_by_dataset[ds] = items
        split_files[ds] = sf
    return items_by_dataset, split_files


def _make_grader(cfg: ExperimentConfig):
    if cfg.grader == "stub":
        return build_grader("stub")
    from src.utils.config import get_settings

    settings = get_settings()
    if cfg.grader == "inprocess":
        return build_grader("inprocess", model=cfg.model, provider=cfg.provider,
                            temperature=cfg.temperature, context_mode=cfg.context_mode,
                            settings=settings)
    return build_grader("http", api_url=settings.client.api_url,
                        token=settings.client.api_token)


def _embedding_model(cfg: ExperimentConfig) -> Optional[str]:
    if cfg.grader != "inprocess":
        return None
    from src.utils.config import get_settings

    return get_settings().embeddings.model


def _print_plan(plan: RunPlan) -> None:
    cfg = plan.config
    print(f"experiment: {cfg.name} (config hash {plan.config_hash})")
    print(f"out dir: {plan.out_dir}")
    per: Dict[Tuple[str, str], int] = {}
    for item in plan.items:
        per[(item.dataset, item.split)] = per.get((item.dataset, item.split), 0) + 1
    for (ds, split), n in sorted(per.items()):
        print(f"  {ds}/{split}: {n} items")
    print(f"planned calls: {len(plan.pairs())} (repeats {cfg.repeats})")
    print(f"estimated cost: ${plan.estimated_cost_usd:.4f} (max_cost_usd ${cfg.max_cost_usd:.4f})")


def _confirm(yes: bool) -> bool:
    if yes:
        return True
    stdin = sys.stdin
    if stdin is None or not stdin.isatty():
        raise CliError("stdin is not a terminal; pass --yes to run without confirmation")
    answer = input("Proceed? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _write_meta(plan: RunPlan, config_file: Path, split_files: Dict[str, SplitFile],
                snapshots: Dict[str, str]) -> None:
    meta = {
        "config_file": str(Path(config_file).resolve()),
        "config": dataclasses.asdict(plan.config),
        "config_hash": plan.config_hash,
        "snapshots": snapshots,
        "split_files": {ds: dataclasses.asdict(sf) for ds, sf in sorted(split_files.items())},
        "embedding_model": _embedding_model(plan.config),
    }
    out_dir = Path(plan.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / RUN_META_FILE).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n",
                                         encoding="utf-8")


def _execute(config_file: Path, out_root: Path, yes: bool) -> Tuple[int, Optional[RunPlan]]:
    cfg = load_experiment(Path(config_file))
    # Checked before any item is loaded: the run directory lives inside out_root.
    assert_output_allowed(cfg.datasets, Path(out_root))
    items_by_dataset, split_files = _load_prepared(cfg)
    plan = plan_run(cfg, items_by_dataset, Path(out_root))
    _print_plan(plan)
    if plan.estimated_cost_usd > cfg.max_cost_usd:
        raise BudgetError(f"estimated cost ${plan.estimated_cost_usd:.4f} exceeds "
                          f"max_cost_usd ${cfg.max_cost_usd:.4f}")
    if not _confirm(yes):
        print("Aborted.")
        return 1, None
    snapshots = {ds: sf.snapshot for ds, sf in sorted(split_files.items())}
    _write_meta(plan, config_file, split_files, snapshots)
    grader = _make_grader(cfg)
    try:
        summary = run(plan, grader)
    finally:
        grader.close()
    print(f"graded: {summary.graded}, skipped (already done): {summary.skipped_existing}")
    if summary.failures:
        print(f"failures: {json.dumps(summary.failures, sort_keys=True)}")
    print(f"cost: ${summary.cost_usd:.4f} (this invocation ${summary.cost_usd_this_run:.4f}), "
          f"tokens in {summary.tokens_in}, out {summary.tokens_out}")
    if summary.aborted:
        print(f"aborted: {summary.aborted}; re-run the same command to resume")
        return 1, plan
    print(f"results: {plan.out_dir}")
    return 0, plan


def cmd_run(args: argparse.Namespace) -> int:
    out_root = args.out_root if args.out_root is not None else DEFAULT_RUNS_ROOT
    return _execute(args.experiment, out_root, args.yes)[0]


# --------------------------------------------------------------------------- report

def _load_meta(run_dir: Path) -> dict:
    path = Path(run_dir) / RUN_META_FILE
    if not path.exists():
        raise CliError(f"{RUN_META_FILE} not found in {run_dir}; "
                       "was it produced by `python -m src.evaluation run`?")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_for_report(run_dir: Path):
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise CliError(f"run directory not found: {run_dir}")
    meta = _load_meta(run_dir)
    try:
        results, summary = load_run(run_dir)
    except FileNotFoundError as exc:
        raise CliError(f"incomplete run directory {run_dir}: {Path(exc.filename).name} missing")
    cfg = ExperimentConfig(**meta["config"])
    h = meta["config_hash"]
    if any(r.config_hash != h for r in results):
        raise CliError(f"results in {run_dir} do not belong to config hash {h}")
    if config_hash(cfg, meta["snapshots"]) != h:
        print("warning: the prompt templates changed since this run; the manifest records "
              "the current prompt hash", file=sys.stderr)
    split_files = {ds: SplitFile(**sf) for ds, sf in meta["split_files"].items()}
    return meta, cfg, results, summary, split_files


def _report(run_dir: Path, out_base: Optional[Path],
            thresholds_from: Optional[Path] = None,
            override: Optional[FittedThresholds] = None,
            n_resamples: Optional[int] = None):
    meta, cfg, results, summary, split_files = _load_for_report(run_dir)
    if thresholds_from is not None:
        override = load_report_thresholds(Path(thresholds_from))
    fitted = fit_run_thresholds(results, cfg.datasets)
    kwargs = {} if n_resamples is None else {"n_resamples": n_resamples}
    agg = aggregate(results, cfg, fitted, thresholds_override=override, **kwargs)
    manifest = build_manifest(cfg, meta["config_hash"], summary, split_files, meta["snapshots"],
                              embedding_model=meta.get("embedding_model"),
                              thresholds=override if override is not None else fitted,
                              config_file=Path(meta["config_file"]), results=results)
    if out_base is None:
        out_base = REPORTS_DIR / f"{date.today().isoformat()}-{cfg.phase}-{cfg.name}"
    md_path, json_path = write_report(agg, manifest, Path(out_base))
    print(f"report: {md_path}")
    print(f"report: {json_path}")
    return agg, manifest


def cmd_report(args: argparse.Namespace) -> int:
    _report(args.run_dir, args.out, thresholds_from=args.thresholds_from)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    if not args.run_dir or len(args.run_dir) != 2:
        raise CliError("compare needs exactly two --run-dir arguments (A, then B)")
    sides = []
    for d in args.run_dir:
        meta, cfg, results, _, _ = _load_for_report(d)
        sides.append((f"{cfg.name}-{meta['config_hash']}", cfg, results,
                      fit_run_thresholds(results, cfg.datasets)))
    (name_a, _, ra, ta), (name_b, _, rb, tb) = sides
    rows = compare_runs(ra, rb, ta, tb)
    table = render_comparison(rows, compare_counts(ra, rb))
    text = f"# Comparison\n\n- A: `{name_a}`\n- B: `{name_b}`\n\n{table}\n"
    print(text)
    if args.out is not None:
        out = Path(args.out)
        if out.suffix != ".md":
            out = out.with_name(out.name + ".md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"comparison: {out}")
    return 0


# --------------------------------------------------------------------------- smoke

def _fit_on_split(results: Sequence[EvalResult], datasets, split: str) -> FittedThresholds:
    fitted = {}
    for ds in sorted(datasets):
        sel = [r for r in results if r.dataset == ds and r.split == split and r.success
               and r.score is not None and r.derived_from is None and r.repeat == 0]
        if sel:
            fitted[ds] = fit_thresholds([r.score for r in sel], [r.gold_label for r in sel],
                                        f"{ds}/{split}")
    return FittedThresholds(fitted, source=f"{split} split (CI plumbing check, not an evaluation)")


def _diff(expected: Any, actual: Any, path: str, out: List[str]) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in sorted(set(expected) | set(actual)):
            p = f"{path}.{k}" if path else str(k)
            if k not in actual:
                out.append(f"{p}: missing (expected {expected[k]!r})")
            elif k not in expected:
                out.append(f"{p}: unexpected (got {actual[k]!r})")
            else:
                _diff(expected[k], actual[k], p, out)
        return
    if expected is None or actual is None:
        if expected is not actual:
            out.append(f"{path}: expected {expected!r}, got {actual!r}")
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) \
            and not isinstance(expected, bool) and not isinstance(actual, bool):
        if not math.isclose(expected, actual, rel_tol=1e-9, abs_tol=1e-12):
            out.append(f"{path}: expected {expected!r}, got {actual!r}")
        return
    if expected != actual:
        out.append(f"{path}: expected {expected!r}, got {actual!r}")


def cmd_smoke(args: argparse.Namespace) -> int:
    print(f"note: {SMOKE_LABEL}")
    with tempfile.TemporaryDirectory(prefix="eval-smoke-") as tmp:
        tmp_path = Path(tmp)
        _prepare("synthetic", None, None, tmp_path / "prepared", refreeze=False)
        code, plan = _execute(SMOKE_CONFIG, tmp_path / "runs", yes=True)
        if code != 0 or plan is None:
            _err("smoke run did not complete")
            return 1
        results, _ = load_run(plan.out_dir)
        override = _fit_on_split(results, plan.config.datasets, "smoke")
        agg, manifest = _report(plan.out_dir, tmp_path / "report" / "smoke", override=override,
                                n_resamples=SMOKE_RESAMPLES)
        metrics = json.loads(json.dumps(render_json(agg, manifest)["metrics"]))

    if args.write is not None:
        body = {"note": SMOKE_LABEL, "n_resamples": SMOKE_RESAMPLES, "metrics": metrics}
        Path(args.write).parent.mkdir(parents=True, exist_ok=True)
        Path(args.write).write_text(json.dumps(body, indent=2, sort_keys=True) + "\n",
                                    encoding="utf-8")
        print(f"wrote expected summary: {args.write}")
        return 0
    expected = json.loads(Path(args.check).read_text(encoding="utf-8"))
    problems: List[str] = []
    _diff(expected.get("metrics"), metrics, "", problems)
    if problems:
        print(f"smoke summary differs from {args.check} ({len(problems)} keys):")
        for line in problems:
            print(f"  {line}")
        return 1
    print(f"smoke summary matches {args.check}")
    return 0


# --------------------------------------------------------------------------- canaries

def cmd_canaries(args: argparse.Namespace) -> int:
    if not args.from_prepared:
        raise CliError("canaries needs --from-prepared")
    answers: List[List[str]] = []
    for ds in CANARY_DATASETS:
        path = PREPARED_DIR / f"{ds}.jsonl"
        if path.exists():
            answers.extend(words for words in (i.answer.split() for i in read_items(path))
                           if len(words) >= CANARY_WORDS)
    if not answers:
        raise CliError("no prepared private items with answers of 8+ words; run prepare first")
    rng = random.Random(DEFAULT_SEED)
    seen = set()
    for _ in range(CANARY_COUNT):
        words = rng.choice(answers)
        start = rng.randrange(len(words) - CANARY_WORDS + 1)
        snippet = " ".join(words[start:start + CANARY_WORDS])
        if snippet not in seen:
            seen.add(snippet)
            print(snippet)
    return 0


# --------------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.evaluation",
                                     description="RAGrader offline evaluation harness")
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="{prepare,run,report,compare,smoke}")

    p = sub.add_parser("prepare", help="load, clean and split a dataset; freeze its split file")
    p.add_argument("--dataset", required=True, choices=sorted(DATASETS))
    p.add_argument("--source", type=Path, help="source CSV (or the SciEntsBank cache dir)")
    p.add_argument("--reference-pdf", type=Path, help="jk_case reference answer PDF")
    p.add_argument("--out", type=Path, help="directory for the prepared items")
    p.add_argument("--refreeze", action="store_true",
                   help="replace a frozen split file whose snapshot changed")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("run", help="grade an experiment configuration (resumable)")
    p.add_argument("--experiment", required=True, type=Path)
    p.add_argument("--out-root", type=Path, help=f"default: {DEFAULT_RUNS_ROOT}")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="write the aggregate Markdown + JSON report of a run")
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--out", type=Path,
                   help="output base path (default docs/evaluation/<date>-<phase>-<name>)")
    p.add_argument("--thresholds-from", type=Path,
                   help="baseline report .json whose frozen thresholds this report uses")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("compare", help="paired B - A differences between two runs")
    p.add_argument("--run-dir", action="append", type=Path, help="give twice: A, then B")
    p.add_argument("--out", type=Path, help="write the comparison to this .md file")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("smoke", help="CI smoke check: stub grader on the synthetic set")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", type=Path, help="compare against this expected summary")
    g.add_argument("--write", type=Path, help="regenerate this expected summary")
    p.set_defaults(func=cmd_smoke)

    # Hidden helper. No ``help=`` at all: on Python 3.12 ``help=argparse.SUPPRESS`` still lists
    # the subcommand (as "==SUPPRESS=="); without it, and with the explicit metavar above, it
    # appears in neither the usage line nor the command list.
    p = sub.add_parser("canaries", description=argparse.SUPPRESS)
    p.add_argument("--from-prepared", action="store_true")
    p.set_defaults(func=cmd_canaries)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (CliError, PrivacyError, BudgetError) as exc:
        _err(str(exc))
        return 2
    except (FileNotFoundError, ValueError) as exc:
        _err(f"{type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
