"""Tests for the evaluation CLI (``python -m src.evaluation``).

No real private data is read: private paths are redirected to a throwaway
``private-data/evaluation/_cli_test_<uuid>`` directory holding fixture items.
"""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from src.evaluation import __main__ as cli
from src.evaluation import paths
from src.evaluation.schema import EvalItem, read_items, write_jsonl

EXPECTED = paths.EVAL_ASSETS / "synthetic" / "expected_summary.json"
WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
         "mike november oscar papa quebec romeo sierra tango").split()


def _engsaf_items(n_questions=6, per_question=6, tag="x"):
    items = []
    for q in range(n_questions):
        for a in range(per_question):
            words = [WORDS[(q + a + k) % len(WORDS)] for k in range(12)]
            items.append(EvalItem(
                item_id=f"eng-{q}-{a}", dataset="engsaf", question_id=f"eq-{q}",
                question=f"fixture question {q}", answer=" ".join(words) + f" {tag}",
                language="en", gold_label=a % 3, label_scale=3, split="train",
                reference_text=" ".join(WORDS[q:q + 8]),
            ))
    return items


def _run(argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    stdin = io.StringIO("") if stdin is None else stdin
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch("sys.stdin", stdin):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class _PrivateSandbox(unittest.TestCase):
    """Redirects every private path constant of the CLI into a temp dir under private-data/."""

    def setUp(self):
        self.root = paths.PRIVATE_DIR / "evaluation" / f"_cli_test_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True)
        self.tmp = Path(tempfile.mkdtemp())
        self.public_splits = self.tmp / "public_splits"
        patches = {
            "PREPARED_DIR": self.root / "prepared",
            "PRIVATE_SPLITS_DIR": self.root / "splits",
            "PUBLIC_SPLITS_DIR": self.public_splits,
            "CHECKSUMS_FILE": self.public_splits / "private_checksums.json",
            "DEFAULT_RUNS_ROOT": self.root / "runs",
        }
        for name, value in patches.items():
            p = mock.patch.object(cli, name, value)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_config(self, name="cli-engsaf", grader="stub", datasets="engsaf: [dev, test]",
                     extra=""):
        path = self.tmp / f"{name}.yaml"
        path.write_text(
            f"name: {name}\nphase: \"4a\"\ngrader: {grader}\nprovider: stub\n"
            f"datasets:\n  {datasets}\nconcurrency: 1\nmax_cost_usd: 0.0\n{extra}",
            encoding="utf-8")
        return path

    def prepare_engsaf(self, items=None):
        items = _engsaf_items() if items is None else items
        with mock.patch.object(cli, "_load_source", return_value=(items, {"items": len(items)})):
            return _run(["prepare", "--dataset", "engsaf"])


class SmokeTest(unittest.TestCase):
    def test_smoke_check_matches_expected(self):
        code, out, err = _run(["smoke", "--check", str(EXPECTED)])
        self.assertEqual(0, code, out + err)
        self.assertIn("not an evaluation", out)

    def test_smoke_check_detects_mutation(self):
        data = json.loads(EXPECTED.read_text(encoding="utf-8"))
        metric = data["metrics"]["synthetic"]["smoke"]
        name = sorted(k for k, v in metric.items() if isinstance(v.get("value"), float))[0]
        metric[name]["value"] += 0.01
        with tempfile.TemporaryDirectory() as d:
            mutated = Path(d) / "expected.json"
            mutated.write_text(json.dumps(data), encoding="utf-8")
            code, out, err = _run(["smoke", "--check", str(mutated)])
        self.assertEqual(1, code)
        self.assertIn(f"synthetic.smoke.{name}.value", out + err)

    def test_smoke_write_then_check_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "expected.json"
            self.assertEqual(0, _run(["smoke", "--write", str(target)])[0])
            self.assertEqual(0, _run(["smoke", "--check", str(target)])[0])

    def test_smoke_does_not_import_pyarrow_or_real_graders(self):
        # backend-tests installs only requirements.txt (no pyarrow); graders are built lazily.
        import subprocess
        import sys
        code = ("import sys; from src.evaluation.__main__ import main; "
                "main(['smoke', '--check', 'evaluation/synthetic/expected_summary.json']); "
                "bad = [m for m in sys.modules if m.split('.')[0] == 'pyarrow' or m in "
                "('src.evaluation.graders.inprocess', 'src.grading.grader')]; "
                "print('BAD', bad)")
        proc = subprocess.run([sys.executable, "-c", code], cwd=paths.BACKEND_DIR,
                              capture_output=True, text=True, timeout=300)
        self.assertIn("BAD []", proc.stdout, proc.stderr[-2000:])


class RunPrivacyTest(_PrivateSandbox):
    def test_run_private_dataset_outside_private_data_exits_before_grading(self):
        self.assertEqual(0, self.prepare_engsaf()[0])
        cfg = self.write_config()
        with mock.patch.object(cli, "build_grader") as build:
            code, out, err = _run(["run", "--experiment", str(cfg),
                                   "--out-root", str(self.tmp / "x"), "--yes"])
        self.assertEqual(2, code)
        self.assertIn("private-data/", err)
        build.assert_not_called()
        self.assertFalse((self.tmp / "x").exists())

    def test_run_never_prints_item_text(self):
        self.prepare_engsaf()
        cfg = self.write_config()
        code, out, err = _run(["run", "--experiment", str(cfg), "--yes"])
        self.assertEqual(0, code, err)
        for word in ("fixture question", "alpha bravo"):
            self.assertNotIn(word, out + err)


class RunTest(_PrivateSandbox):
    def test_missing_prepared_file_exits_2(self):
        cfg = self.write_config()
        code, out, err = _run(["run", "--experiment", str(cfg), "--yes"])
        self.assertEqual(2, code)
        self.assertIn("prepare --dataset engsaf", err)

    def test_non_tty_without_yes_refuses(self):
        self.prepare_engsaf()
        cfg = self.write_config()
        with mock.patch.object(cli, "build_grader") as build:
            code, out, err = _run(["run", "--experiment", str(cfg)])
        self.assertEqual(2, code)
        self.assertIn("--yes", err)
        build.assert_not_called()

    def test_tty_answer_no_aborts(self):
        self.prepare_engsaf()
        cfg = self.write_config()
        stdin = io.StringIO("n\n")
        stdin.isatty = lambda: True
        with mock.patch.object(cli, "build_grader") as build, \
                mock.patch("builtins.input", return_value="n"):
            code, out, err = _run(["run", "--experiment", str(cfg)], stdin=stdin)
        self.assertEqual(1, code)
        build.assert_not_called()

    def test_run_prints_plan_and_closes_grader(self):
        from src.evaluation.graders.stub import StubGrader

        self.prepare_engsaf()
        cfg = self.write_config()
        grader = StubGrader()
        grader.close = mock.Mock()
        with mock.patch.object(cli, "build_grader", return_value=grader):
            code, out, err = _run(["run", "--experiment", str(cfg), "--yes"])
        self.assertEqual(0, code, err)
        self.assertIn("calls", out)
        self.assertIn("estimated cost", out)
        grader.close.assert_called_once()
        run_dirs = list((self.root / "runs").iterdir())
        self.assertEqual(1, len(run_dirs))
        self.assertTrue((run_dirs[0] / "results.jsonl").exists())
        self.assertTrue((run_dirs[0] / cli.RUN_META_FILE).exists())

    def test_grader_closed_when_run_raises(self):
        self.prepare_engsaf()
        cfg = self.write_config()
        grader = mock.Mock()
        with mock.patch.object(cli, "build_grader", return_value=grader), \
                mock.patch.object(cli, "run", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                _run(["run", "--experiment", str(cfg), "--yes"])
        grader.close.assert_called_once()

    def test_budget_error_exits_2_without_building_grader(self):
        self.prepare_engsaf()
        cfg = self.write_config(extra="price_in_per_mtok: 1000\n")
        with mock.patch.object(cli, "build_grader") as build:
            code, out, err = _run(["run", "--experiment", str(cfg), "--yes"])
        self.assertEqual(2, code)
        self.assertIn("max_cost_usd", err)
        build.assert_not_called()

    def test_stale_prepared_items_exit_2(self):
        self.prepare_engsaf()
        prepared = cli.PREPARED_DIR / "engsaf.jsonl"
        items = read_items(prepared)
        write_jsonl(prepared, items[1:])
        cfg = self.write_config()
        code, out, err = _run(["run", "--experiment", str(cfg), "--yes"])
        self.assertEqual(2, code)
        self.assertIn("frozen split file", err)

    def test_inprocess_grader_built_from_settings(self):
        cfg = cli.load_experiment(self.write_config(grader="inprocess"))
        settings = mock.Mock()
        with mock.patch("src.utils.config.get_settings", return_value=settings), \
                mock.patch.object(cli, "build_grader") as build:
            cli._make_grader(cfg)
        build.assert_called_once_with("inprocess", model=cfg.model, provider=cfg.provider,
                                      temperature=cfg.temperature,
                                      context_mode=cfg.context_mode, settings=settings,
                                      requests_per_minute=None)

    def test_http_grader_built_from_client_settings(self):
        cfg = cli.load_experiment(self.write_config(grader="http"))
        settings = mock.Mock()
        settings.client.api_url = "http://127.0.0.1:9"
        settings.client.api_token = "t"
        with mock.patch("src.utils.config.get_settings", return_value=settings), \
                mock.patch.object(cli, "build_grader") as build:
            cli._make_grader(cfg)
        build.assert_called_once_with("http", api_url="http://127.0.0.1:9", token="t")


class RunMetaTest(_PrivateSandbox):
    def _meta(self):
        run_dir = next((self.root / "runs").iterdir())
        return run_dir, json.loads((run_dir / cli.RUN_META_FILE).read_text())

    def test_meta_records_prompt_hash_effective_settings_and_first_start(self):
        from src.evaluation.experiment import prompt_template_hash
        self.prepare_engsaf()
        cfg = self.write_config()
        self.assertEqual(0, _run(["run", "--experiment", str(cfg), "--yes"])[0])
        run_dir, meta = self._meta()
        self.assertEqual(prompt_template_hash(), meta["prompt_template_sha256"])
        self.assertEqual({"grader": "stub"}, meta["effective_settings"])
        first = meta["started_at"]
        self.assertTrue(first)
        # Resume: started_at is the first run's, not this invocation's.
        self.assertEqual(0, _run(["run", "--experiment", str(cfg), "--yes"])[0])
        _, meta2 = self._meta()
        self.assertEqual(first, meta2["started_at"])
        base = self.tmp / "rep"
        with mock.patch("src.evaluation.report.prompt_template_hash", return_value="f" * 64):
            code, out, err = _run(["report", "--run-dir", str(run_dir), "--out", str(base)])
        self.assertEqual(0, code, err)
        manifest = json.loads((self.tmp / "rep.json").read_text())["manifest"]
        self.assertEqual(prompt_template_hash(), manifest["prompt_template_sha256"])
        self.assertEqual(first, manifest["started_at"])
        self.assertEqual({"grader": "stub"}, manifest["effective_settings"])

    def test_old_meta_without_prompt_hash_falls_back_with_warning(self):
        self.prepare_engsaf()
        cfg = self.write_config()
        self.assertEqual(0, _run(["run", "--experiment", str(cfg), "--yes"])[0])
        run_dir, meta = self._meta()
        for k in ("prompt_template_sha256", "started_at", "effective_settings"):
            meta.pop(k)
        (run_dir / cli.RUN_META_FILE).write_text(json.dumps(meta))
        with mock.patch("src.evaluation.report.prompt_template_hash", return_value="f" * 64), \
                mock.patch("src.evaluation.__main__.config_hash", return_value="x"):
            code, out, err = _run(["report", "--run-dir", str(run_dir),
                                   "--out", str(self.tmp / "old")])
        self.assertEqual(0, code, err)
        self.assertIn("current prompt hash", err)
        manifest = json.loads((self.tmp / "old.json").read_text())["manifest"]
        self.assertEqual("f" * 64, manifest["prompt_template_sha256"])

    def test_resume_refuses_changed_effective_settings_before_touching_files(self):
        self.prepare_engsaf()
        cfg = self.write_config()
        with mock.patch.object(cli, "_effective_settings", return_value={"chunk_size": 500}):
            self.assertEqual(0, _run(["run", "--experiment", str(cfg), "--yes"])[0])
        run_dir, _ = self._meta()
        before = {p.name: p.read_bytes() for p in run_dir.iterdir() if p.is_file()}
        with mock.patch.object(cli, "_effective_settings", return_value={"chunk_size": 800}), \
                mock.patch.object(cli, "build_grader") as build:
            code, out, err = _run(["run", "--experiment", str(cfg), "--yes"])
        self.assertEqual(2, code)
        self.assertIn("effective settings", err)
        self.assertIn("chunk_size", err)
        build.assert_not_called()
        after = {p.name: p.read_bytes() for p in run_dir.iterdir() if p.is_file()}
        self.assertEqual(before, after)


class PrepareTest(_PrivateSandbox):
    def test_prepare_private_writes_prepared_split_and_checksum(self):
        code, out, err = self.prepare_engsaf()
        self.assertEqual(0, code, err)
        self.assertTrue((cli.PREPARED_DIR / "engsaf.jsonl").exists())
        split = cli.PRIVATE_SPLITS_DIR / "engsaf.json"
        self.assertTrue(json.loads(split.read_text())["hashed"])
        sums = json.loads(cli.CHECKSUMS_FILE.read_text())
        import hashlib
        self.assertEqual(hashlib.sha256(split.read_bytes()).hexdigest(), sums["engsaf"])
        self.assertIn("dev", out)
        self.assertNotIn("alpha bravo", out + err)

    def test_prepare_frozen_split_refuses_changed_snapshot(self):
        self.assertEqual(0, self.prepare_engsaf()[0])
        self.assertEqual(0, self.prepare_engsaf()[0])  # unchanged snapshot is fine
        before = (cli.PRIVATE_SPLITS_DIR / "engsaf.json").read_text()
        code, out, err = self.prepare_engsaf(_engsaf_items(tag="changed"))
        self.assertEqual(2, code)
        self.assertIn("split file is frozen; snapshot changed", err)
        self.assertEqual(before, (cli.PRIVATE_SPLITS_DIR / "engsaf.json").read_text())

    def test_prepare_checksum_mismatch_without_private_split_refuses(self):
        self.assertEqual(0, self.prepare_engsaf()[0])
        (cli.PRIVATE_SPLITS_DIR / "engsaf.json").unlink()
        code, out, err = self.prepare_engsaf(_engsaf_items(tag="changed"))
        self.assertEqual(2, code)
        self.assertIn("split file is frozen; snapshot changed", err)

    def test_prepare_refreeze_overwrites(self):
        self.prepare_engsaf()
        items = _engsaf_items(tag="changed")
        with mock.patch.object(cli, "_load_source", return_value=(items, {})):
            code, out, err = _run(["prepare", "--dataset", "engsaf", "--refreeze"])
        self.assertEqual(0, code, err)

    def test_prepare_public_split_file_in_clear(self):
        items = [EvalItem(item_id=f"sb-{i}", dataset="scientsbank", question_id=f"sq-{i % 3}",
                          question="q", answer="a b c", language="en", gold_label=i % 3,
                          label_scale=3, split="train", reference_text="r")
                 for i in range(12)]
        with mock.patch.object(cli, "_load_source", return_value=(items, {})):
            code, out, err = _run(["prepare", "--dataset", "scientsbank"])
        self.assertEqual(0, code, err)
        data = json.loads((self.public_splits / "scientsbank.json").read_text())
        self.assertIn("sb-0", json.dumps(data))
        self.assertTrue((cli.PREPARED_DIR / "scientsbank.jsonl").exists())

    def test_prepare_jk_case_stages_reference_by_name_and_hash(self):
        import csv
        import hashlib
        src = self.tmp / "case-src"
        src.mkdir()
        with open(src / "case.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["soal", "jawaban", "nilai"])
            for k in range(6):
                w.writerow([f"invented question {k % 2}", f"invented answer {k}", str(4 * k)])
        (src / "key.pdf").write_bytes(b"%PDF-1.4 invented")
        code, out, err = _run(["prepare", "--dataset", "jk_case", "--source",
                               str(src / "case.csv"), "--reference-pdf", str(src / "key.pdf")])
        self.assertEqual(0, code, err)
        staged = self.root / "prepared" / "references" / "key.pdf"
        self.assertEqual(b"%PDF-1.4 invented", staged.read_bytes())
        items = read_items(self.root / "prepared" / "jk_case.jsonl")
        self.assertEqual({"key.pdf"}, {i.reference_document for i in items})
        self.assertEqual({hashlib.sha256(b"%PDF-1.4 invented").hexdigest()},
                         {i.reference_sha256 for i in items})
        self.assertNotIn(str(src), (self.root / "prepared" / "jk_case.jsonl").read_text())

    def test_prepare_synthetic_to_out(self):
        out_dir = self.tmp / "syn"
        code, out, err = _run(["prepare", "--dataset", "synthetic", "--out", str(out_dir)])
        self.assertEqual(0, code, err)
        self.assertEqual(30, len(read_items(out_dir / "synthetic.jsonl")))

    def test_prepare_private_out_outside_private_data_refused(self):
        items = _engsaf_items()
        with mock.patch.object(cli, "_load_source", return_value=(items, {})):
            code, out, err = _run(["prepare", "--dataset", "engsaf", "--out",
                                   str(self.tmp / "leak")])
        self.assertEqual(2, code)
        self.assertFalse((self.tmp / "leak").exists())


class CanariesTest(_PrivateSandbox):
    def test_canaries_prints_snippets_and_writes_nothing(self):
        self.prepare_engsaf()
        before = sorted(p for p in self.root.rglob("*"))
        code, out, err = _run(["canaries", "--from-prepared"])
        self.assertEqual(0, code, err)
        lines = out.splitlines()
        self.assertTrue(0 < len(lines) <= 50)
        answers = [i.answer for i in read_items(cli.PREPARED_DIR / "engsaf.jsonl")]
        for line in lines:
            self.assertEqual(8, len(line.split()))
            self.assertTrue(any(line in " ".join(a.split()) for a in answers))
        self.assertEqual(before, sorted(p for p in self.root.rglob("*")))
        self.assertEqual(lines, _run(["canaries", "--from-prepared"])[1].splitlines())

    def test_canaries_hidden_from_help(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            cli.main(["--help"])
        self.assertNotIn("canaries", buf.getvalue())

    def test_canaries_without_prepared_files_exits_2(self):
        code, out, err = _run(["canaries", "--from-prepared"])
        self.assertEqual(2, code)


class ReportCompareTest(_PrivateSandbox):
    def setUp(self):
        super().setUp()
        self.prepare_engsaf()
        cfg = self.write_config()
        self.assertEqual(0, _run(["run", "--experiment", str(cfg), "--yes"])[0])
        self.run_dir = next((self.root / "runs").iterdir())

    def test_report_writes_md_and_json(self):
        base = self.tmp / "reports" / "r1"
        code, out, err = _run(["report", "--run-dir", str(self.run_dir), "--out", str(base)])
        self.assertEqual(0, code, err)
        data = json.loads((self.tmp / "reports" / "r1.json").read_text())
        self.assertIn("engsaf", data["metrics"])
        self.assertIn("engsaf", data["manifest"]["thresholds"])
        md = (self.tmp / "reports" / "r1.md").read_text()
        self.assertNotIn("alpha bravo", md)
        self.assertNotIn("fixture question", md)

    def test_report_thresholds_from_baseline(self):
        base = self.tmp / "reports" / "base"
        _run(["report", "--run-dir", str(self.run_dir), "--out", str(base)])
        baseline = json.loads((self.tmp / "reports" / "base.json").read_text())
        baseline["thresholds"]["engsaf"].update({"t1": 11.0, "t2": 22.0})
        frozen = self.tmp / "reports" / "frozen.json"
        frozen.write_text(json.dumps(baseline))
        out_base = self.tmp / "reports" / "variant"
        code, out, err = _run(["report", "--run-dir", str(self.run_dir), "--out",
                               str(out_base), "--thresholds-from", str(frozen)])
        self.assertEqual(0, code, err)
        data = json.loads((self.tmp / "reports" / "variant.json").read_text())
        self.assertEqual(11.0, data["thresholds"]["engsaf"]["t1"])
        self.assertEqual(11.0, data["manifest"]["thresholds"]["engsaf"]["t1"])
        self.assertIsNotNone(data["manifest"]["thresholds_source"])

    def test_report_default_out_is_dated_under_reports_dir(self):
        with mock.patch.object(cli, "REPORTS_DIR", self.tmp / "docs"):
            code, out, err = _run(["report", "--run-dir", str(self.run_dir)])
        self.assertEqual(0, code, err)
        names = [p.name for p in (self.tmp / "docs").iterdir()]
        self.assertTrue(any(n.endswith("-4a-cli-engsaf.json") for n in names), names)

    def test_report_missing_run_dir_exits_2(self):
        code, out, err = _run(["report", "--run-dir", str(self.tmp / "nope")])
        self.assertEqual(2, code)

    def test_compare_two_runs(self):
        out_path = self.tmp / "cmp.md"
        code, out, err = _run(["compare", "--run-dir", str(self.run_dir), "--run-dir",
                               str(self.run_dir), "--out", str(out_path)])
        self.assertEqual(0, code, err)
        self.assertIn("Difference (B - A)", out_path.read_text())
        self.assertIn("A failures", out_path.read_text())

    def test_compare_requires_two_run_dirs(self):
        code, out, err = _run(["compare", "--run-dir", str(self.run_dir)])
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
