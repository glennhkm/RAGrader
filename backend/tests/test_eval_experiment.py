import dataclasses
import tempfile
import unittest
from pathlib import Path

from src.evaluation.experiment import (
    ExperimentConfig,
    config_hash,
    load_experiment,
    prompt_template_hash,
)
from src.evaluation.paths import EVAL_ASSETS

EXP_DIR = EVAL_ASSETS / "experiments"
SNAP = {"engsaf": "aaa", "scientsbank": "bbb"}

MINIMAL = """
name: x
phase: "4a"
grader: stub
provider: stub
datasets: {synthetic: [smoke]}
"""


def _write(text):
    d = tempfile.mkdtemp()
    p = Path(d) / "x.yaml"
    p.write_text(text, encoding="utf-8")
    return p


class ExperimentTests(unittest.TestCase):
    def test_all_committed_yamls_load_and_names_match(self):
        files = sorted(EXP_DIR.glob("*.yaml"))
        self.assertEqual(len(files), 8)
        for f in files:
            cfg = load_experiment(f)
            self.assertIsInstance(cfg, ExperimentConfig)
            self.assertEqual(cfg.name, f.stem)
            self.assertEqual(cfg.phase, "4a")

    def test_pinned_values(self):
        c = load_experiment(EXP_DIR / "baseline-gpt-4.1-mini.yaml")
        self.assertEqual((c.model, c.price_in_per_mtok, c.price_out_per_mtok),
                         ("openai/gpt-4.1-mini", 0.40, 1.60))
        c = load_experiment(EXP_DIR / "consistency-gpt-oss-120b.yaml")
        self.assertEqual((c.repeats, c.variant_set), (3, "consistency"))
        c = load_experiment(EXP_DIR / "oracle-gpt-oss-120b.yaml")
        self.assertNotIn("jk_case", c.datasets)
        self.assertEqual(c.context_mode, "oracle")
        c = load_experiment(EXP_DIR / "smoke-stub.yaml")
        self.assertEqual((c.provider, c.model, c.max_cost_usd, c.concurrency),
                         ("stub", None, 0.0, 1))

    def test_defaults_and_required(self):
        c = load_experiment(_write(MINIMAL))
        self.assertEqual((c.repeats, c.variant_set, c.temperature, c.overrides,
                          c.concurrency, c.max_cost_usd, c.context_mode),
                         (1, None, None, {}, 4, 5.0, "rag"))
        with self.assertRaisesRegex(ValueError, "missing key: provider"):
            load_experiment(_write(MINIMAL.replace("provider: stub\n", "")))

    def test_unknown_key_and_bad_values(self):
        with self.assertRaisesRegex(ValueError, "unknown key: bogus"):
            load_experiment(_write(MINIMAL + "bogus: 1\n"))
        with self.assertRaises(ValueError):
            load_experiment(_write(MINIMAL.replace("grader: stub", "grader: nope")))
        with self.assertRaises(ValueError):
            load_experiment(_write(MINIMAL + "context_mode: x\n"))
        with self.assertRaises(ValueError):
            load_experiment(_write(MINIMAL + "variant_set: x\n"))
        with self.assertRaises(ValueError):
            load_experiment(_write(MINIMAL.replace("synthetic", "nodata")))
        with self.assertRaises(ValueError):
            load_experiment(_write(MINIMAL.replace("smoke", "test_uq")))

    def test_hash_sensitivity(self):
        base = load_experiment(EXP_DIR / "baseline-gpt-oss-120b.yaml")
        h = config_hash(base, SNAP)
        self.assertRegex(h, r"^[0-9a-f]{16}$")
        self.assertEqual(h, config_hash(base, dict(SNAP)))
        self.assertNotEqual(h, config_hash(dataclasses.replace(base, temperature=0.0), SNAP))
        self.assertEqual(h, config_hash(dataclasses.replace(base, concurrency=1, max_cost_usd=1.0), SNAP))
        self.assertNotEqual(h, config_hash(base, {**SNAP, "engsaf": "zzz"}))
        self.assertRegex(prompt_template_hash(), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
