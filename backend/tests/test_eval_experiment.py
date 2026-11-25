import dataclasses
import tempfile
import unittest
from pathlib import Path

from src.evaluation.experiment import (
    ExperimentConfig,
    config_hash,
    effective_settings,
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
        self.assertEqual(len(files), 21)  # 8 original, 7 Way and 6 pinned OpenRouter configs
        for f in files:
            cfg = load_experiment(f)
            self.assertIsInstance(cfg, ExperimentConfig)
            self.assertEqual(cfg.name, f.stem)
            self.assertEqual(cfg.phase, "4a")

    def test_way_configs_are_free_single_endpoint(self):
        way = sorted(EXP_DIR.glob("way-*.yaml"))
        self.assertEqual(len(way), 7)
        for f in way:
            c = load_experiment(f)
            self.assertEqual(c.provider, "openai_compatible")
            self.assertIn(c.model, ("openai/gpt-oss-120b", "openai/gpt-oss-20b"))
            self.assertEqual((c.price_in_per_mtok, c.price_out_per_mtok), (0.0, 0.0))
            self.assertLessEqual(c.concurrency, 2)
            self.assertEqual(c.requests_per_minute, 40)
            self.assertNotIn("jk_case", c.datasets)  # student data stays off the gateway
        pilot = load_experiment(EXP_DIR / "way-pilot-gpt-oss-120b.yaml")
        self.assertEqual(pilot.max_items_per_split, 20)

    def test_pinned_openrouter_configs(self):
        files = sorted(EXP_DIR.glob("openrouter-*.yaml"))
        self.assertEqual(len(files), 6)
        for f in files:
            c = load_experiment(f)
            self.assertEqual(c.provider, "openai_compatible")  # no fallback provider
            self.assertNotIn("jk_case", c.datasets)

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

    def test_max_items_per_split_validated(self):
        c = load_experiment(_write(MINIMAL + "max_items_per_split: 50\n"))
        self.assertEqual(50, c.max_items_per_split)
        self.assertIsNone(load_experiment(_write(MINIMAL)).max_items_per_split)
        for bad in ("0", "-3", "2.5", "true", "'50'"):
            with self.assertRaisesRegex(ValueError, "max_items_per_split"):
                load_experiment(_write(MINIMAL + f"max_items_per_split: {bad}\n"))

    def test_max_items_per_split_hashed_only_when_set(self):
        base = load_experiment(EXP_DIR / "baseline-gpt-oss-120b.yaml")
        # Pinned: the hash of an unset limit equals the pre-field hash (no field in payload).
        import hashlib
        import json
        body = dataclasses.asdict(base)
        for k in ("concurrency", "max_cost_usd", "max_items_per_split", "requests_per_minute"):
            body.pop(k)
        blob = json.dumps({"config": body, "prompt": prompt_template_hash(), "data": SNAP},
                          sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(hashlib.sha256(blob.encode()).hexdigest()[:16], config_hash(base, SNAP))
        limited = dataclasses.replace(base, max_items_per_split=50)
        self.assertNotEqual(config_hash(base, SNAP), config_hash(limited, SNAP))

    def test_non_empty_overrides_rejected(self):
        with self.assertRaisesRegex(ValueError, "overrides are not supported until Cycle 4b"):
            load_experiment(_write(MINIMAL + "overrides: {seed: 1}\n"))
        self.assertEqual({}, load_experiment(_write(MINIMAL + "overrides: {}\n")).overrides)
        self.assertEqual({}, load_experiment(_write(MINIMAL + "overrides:\n")).overrides)

    def test_effective_settings_inprocess_reads_settings_never_secrets(self):
        from types import SimpleNamespace as NS
        settings = NS(
            llm=NS(model="default/model", temperature=0.3, max_new_tokens=1024,
                   api_key="sk-SECRET"),
            embeddings=NS(provider="huggingface", model="BAAI/bge-m3", api_key="hf-SECRET",
                          huggingface_token="hf-SECRET"),
            reranker=NS(enabled=False, type="bge", model="bge-reranker-v2-m3", top_k=5,
                        rerank_top_k=3, api_key="SECRET"),
            raw={"document_processing": {"chunk_size": 500, "chunk_overlap": 50}},
        )
        cfg = load_experiment(EXP_DIR / "baseline-gpt-oss-120b.yaml")
        eff = effective_settings(cfg, settings)
        self.assertEqual("openai/gpt-oss-120b", eff["llm_model"])
        self.assertEqual(0.3, eff["llm_temperature"])  # config leaves it unset
        self.assertEqual(("huggingface", "BAAI/bge-m3"),
                         (eff["embedding_provider"], eff["embedding_model"]))
        self.assertEqual((5, False, 3), (eff["retrieval_top_k"], eff["reranking_enabled"],
                                         eff["rerank_top_k"]))
        self.assertEqual((500, 50), (eff["chunk_size"], eff["chunk_overlap"]))
        self.assertNotIn("SECRET", repr(eff))
        pinned = dataclasses.replace(cfg, temperature=0.0, model=None)
        eff = effective_settings(pinned, settings)
        self.assertEqual((0.0, "default/model"), (eff["llm_temperature"], eff["llm_model"]))

    def test_effective_settings_stub_and_http_need_no_settings(self):
        stub = load_experiment(EXP_DIR / "smoke-stub.yaml")
        self.assertEqual({"grader": "stub"}, effective_settings(stub, None))
        http = dataclasses.replace(stub, grader="http")
        self.assertEqual("http", effective_settings(http, None)["grader"])


if __name__ == "__main__":
    unittest.main()
