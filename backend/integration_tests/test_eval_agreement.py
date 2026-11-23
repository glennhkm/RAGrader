"""Eval harness agreement: the ``http`` and ``inprocess`` graders on the stub stack.

Both graders grade the 30 public synthetic items through ``plan_run``/``run``:

* ``http`` goes through HAProxy to the API replicas (stub LLM and embeddings,
  Chroma over HTTP), in the ``v1:<ns>`` namespace.
* ``inprocess`` runs the product ``EssayGrader`` in this process, with settings
  built by ``load_settings(env=...)`` that mirror the API container's environment
  (``.env.example`` plus the CI override), pointed at the stub AI's published
  port. The in-process grader keeps its own embedded Chroma under the run's work
  directory, in the ``eval:<ns>`` course, so it never touches the API's store.

The two configs differ only in ``grader``, so their config hashes, and with them
their namespaces, differ too. Both ingest the same per-question materials.

Per item, ``score``, ``confidence``, ``integrity_warnings`` and
``retrieved_sources`` must be identical.

Environment (same as ``test_full_stack.py``):
    RAG_IT_URL               API base URL (default http://127.0.0.1:8000)
    RAG_IT_TOKEN             Bearer token (default empty)
    RAG_IT_CHROMA_PORT       Published Chroma port (default 18001)
    RAG_IT_STUB_AI_PORT      Published stub-AI port (default 19000)

Skips cleanly when the API is down (fails instead under CI).
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict

import httpx
from dotenv import dotenv_values

BASE_URL = os.environ.get("RAG_IT_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("RAG_IT_TOKEN", "")
CHROMA_PORT = int(os.environ.get("RAG_IT_CHROMA_PORT", "18001"))
STUB_AI_PORT = int(os.environ.get("RAG_IT_STUB_AI_PORT", "19000"))
EXPECT_REPLICAS = int(os.environ.get("RAG_IT_EXPECT_REPLICAS", "0") or 0)
BACKEND = Path(__file__).resolve().parents[1]
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
STUB_URL = f"http://127.0.0.1:{STUB_AI_PORT}/v1"
DATASET = "synthetic"


def setUpModule() -> None:
    try:
        httpx.get(f"{BASE_URL}/health", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001 - any failure means the stack is not up
        if EXPECT_REPLICAS or os.environ.get("CI"):
            # A dead stack in CI must fail the job, never skip every test.
            raise RuntimeError(f"API not reachable at {BASE_URL} in CI: {type(exc).__name__}") from exc
        raise unittest.SkipTest(f"API not reachable at {BASE_URL}: {type(exc).__name__}")
    try:
        httpx.get(f"{STUB_URL[:-3]}/health", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        if EXPECT_REPLICAS or os.environ.get("CI"):
            raise RuntimeError(f"stub AI not reachable at {STUB_URL} in CI: {type(exc).__name__}") from exc
        raise unittest.SkipTest(f"stub AI not reachable at {STUB_URL}: {type(exc).__name__}")


def container_env() -> Dict[str, str]:
    """The API container's environment, as seen from the host.

    The container gets ``.env`` (a copy of ``.env.example`` in CI), then the base
    compose ``environment`` block, then the CI override. Service hostnames are
    replaced by the loopback ports the CI override publishes. Redis is not
    published, so distributed locks are off here; they do not affect results.
    """
    env = {k: v for k, v in dotenv_values(BACKEND / ".env.example").items() if v is not None}
    env.update({
        # docker-compose.yml, api environment
        "ANONYMIZED_TELEMETRY": "false",
        "CHROMA_CLIENT_MODE": "http",
        "CHROMA_HOST": "127.0.0.1",
        "CHROMA_PORT": str(CHROMA_PORT),
        "CHROMA_SSL": "false",
        "DISTRIBUTED_LOCK_ENABLED": "false",
        "LOG_TO_FILE": "false",
        # docker-compose.ci.yml, api environment
        "LLM_PROVIDER": "openai_compatible",
        "LLM_BASE_URL": STUB_URL,
        "LLM_MODEL": "stub",
        "EMBEDDING_PROVIDER": "openai_compatible",
        "EMBEDDING_BASE_URL": STUB_URL,
        "EMBEDDING_MODEL": "stub-embed",
        "API_AUTH_TOKEN": "ci-token",
    })
    return env


def experiment(grader: str):
    from src.evaluation.experiment import ExperimentConfig

    return ExperimentConfig(
        name=f"it-agreement-{grader}", phase="integration", grader=grader, model="stub",
        provider="openai_compatible", context_mode="rag", temperature=None,
        datasets={DATASET: ["smoke"]}, repeats=1, variant_set=None,
        price_in_per_mtok=0.0, price_out_per_mtok=0.0, concurrency=4, max_cost_usd=1.0,
        overrides={},
    )


class EvalAgreementTests(unittest.TestCase):
    def test_http_and_inprocess_graders_agree_on_synthetic(self) -> None:
        from src.evaluation.datasets import load_dataset
        from src.evaluation.graders.http import HttpGrader, http_namespace
        from src.evaluation.graders.inprocess import InProcessGrader
        from src.evaluation.runner import RESULTS_FILE, plan_run, run
        from src.evaluation.schema import read_results
        from src.evaluation.splits import prepare_dataset
        from src.utils.config import load_settings

        raw_items, _ = load_dataset(DATASET, None)
        items, _ = prepare_dataset(DATASET, raw_items)
        self.assertEqual(30, len([i for i in items if i.role == "eval"]))

        tmp = Path(tempfile.mkdtemp(prefix="rag-it-agreement-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

        http_plan = plan_run(experiment("http"), {DATASET: items}, tmp)
        local_plan = plan_run(experiment("inprocess"), {DATASET: items}, tmp)
        http_ns = http_namespace(http_plan.config_hash, DATASET)
        local_ns = http_namespace(local_plan.config_hash, DATASET)
        self.assertNotEqual(http_ns, local_ns)
        self.assertEqual(http_plan.materials, local_plan.materials)
        self.assertEqual(30, len(http_plan.items))

        def drop_namespace() -> None:
            try:
                httpx.delete(f"{BASE_URL}/v1/namespaces/{http_ns}", headers=HEADERS, timeout=60)
            except httpx.HTTPError:
                pass

        drop_namespace()  # a leftover from an interrupted local run
        self.addCleanup(drop_namespace)

        http_grader = HttpGrader(BASE_URL, TOKEN, timeout=120)
        self.addCleanup(http_grader.close)
        http_summary = run(http_plan, http_grader)

        settings = load_settings(env=container_env())
        local_grader = InProcessGrader("stub", provider="openai_compatible", settings=settings)
        self.addCleanup(local_grader.close)
        local_summary = run(local_plan, local_grader)

        self.assertEqual({}, http_summary.failures)
        self.assertEqual({}, local_summary.failures)
        self.assertEqual(30, http_summary.graded)
        self.assertEqual(30, local_summary.graded)

        via_http = {r.item_id: r for r in read_results(http_plan.out_dir / RESULTS_FILE)}
        via_local = {r.item_id: r for r in read_results(local_plan.out_dir / RESULTS_FILE)}
        self.assertEqual(sorted(via_http), sorted(via_local))
        self.assertEqual(30, len(via_http))

        for item_id in sorted(via_http):
            h, p = via_http[item_id], via_local[item_id]
            with self.subTest(item_id=item_id):
                self.assertTrue(h.success and p.success)
                self.assertEqual(h.score, p.score)
                self.assertEqual(h.confidence, p.confidence)
                self.assertEqual(h.integrity_warnings, p.integrity_warnings)
                self.assertEqual(h.retrieved_sources, p.retrieved_sources)
                self.assertTrue(h.retrieved_sources)

        # Non-vacuous: retrieval depends on the item, and usually finds the item's own
        # material. The stub's hashed bag-of-words embeddings do not always rank it
        # in the top k, so this is not asserted per item.
        results = list(via_http.values())
        self.assertGreater(len({r.retrieved_sources for r in results}), 1)
        gold_hits = sum(r.gold_source in r.retrieved_sources for r in results)
        self.assertGreater(gold_hits, len(results) // 2, f"gold source retrieved for {gold_hits}/30")


if __name__ == "__main__":
    unittest.main()
