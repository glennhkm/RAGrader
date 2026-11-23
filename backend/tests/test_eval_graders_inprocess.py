import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.evaluation.graders import build_grader
from src.evaluation.graders.base import GradeRequest, TransientGraderError
from src.evaluation.graders.inprocess import InProcessGrader
from src.evaluation.materials import MaterialDoc, gold_source, source_name
from src.evaluation.schema import EvalItem
from src.utils.config import load_settings

ITEM = EvalItem("i1", "engsaf", "q1", "What does the membrane do?", "a", "en", 1, 3, "dev",
                reference_text="it controls entry")
OTHER = EvalItem("i2", "engsaf", "q2", "What is osmosis?", "b", "en", 1, 3, "dev",
                 reference_text="water diffusion")
REQ = GradeRequest(ITEM.question, "the membrane controls entry", "en")
GOLD_TEXT = "Question: What does the membrane do?\nReference answer: it controls entry"
DOCS = [
    MaterialDoc(source_name("q1"), GOLD_TEXT),
    MaterialDoc(source_name("q2"), "Question: What is osmosis?\nReference answer: water diffusion"),
]
OK_RESULT = {
    "success": True, "score": 80, "confidence": 0.9, "feedback": "good",
    "citations": [{"source": source_name("q1")}],
    "integrity_warnings": ["ungrounded_citations_removed:2"],
    "retrieved_documents": [{"source": source_name("q1")}, {"source": source_name("q2")}],
    "prompt_used": "p" * 400,
}


class _FakeLLM:
    def __init__(self, usage, served="openrouter-upstream", raw="r" * 80):
        self.usage = usage
        self.served = served
        self.raw = raw
        self.last_usage = None
        self.last_served_provider = None
        self._last_provider = None

    def generate(self, prompt):
        self.last_usage = self.usage
        self.last_served_provider = self.served
        self._last_provider = "openrouter"
        return self.raw


class _ProductRetriever:
    def retrieve(self, query, course_id=None, metadata_filter=None):
        return []


class _FakeEssayGrader:
    def __init__(self, config, provider, model_name, settings, result, usage, error):
        self.config = config
        self.provider = provider
        self.model_name = model_name
        self.settings = settings
        self.result = result
        self.error = error
        self.ingested = []
        self.calls = []
        self.rag_pipeline = SimpleNamespace(retriever=_ProductRetriever(), llm=_FakeLLM(usage))

    def ingest_course_materials(self, file_paths, course_id=None):
        self.ingested.append((list(file_paths), course_id))
        return {"success": True}

    def grade_essay(self, question, essay, rubric, course_id=None, metadata_filter=None,
                    language=None):
        self.calls.append(dict(question=question, essay=essay, rubric=rubric,
                               course_id=course_id, language=language))
        if self.error is not None:
            raise self.error
        docs = self.rag_pipeline.retriever.retrieve(f"{question}\n\n{essay}", course_id=course_id)
        self.last_docs = docs
        self.rag_pipeline.llm.generate("prompt")
        return dict(self.result)


class InProcessGraderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.settings = load_settings(env={})

    def _grader(self, result=None, usage=None, error=None, prepare=True, docs=DOCS, **kwargs):
        result = OK_RESULT if result is None else result
        usage = {"prompt_tokens": 1200, "completion_tokens": 150} if usage is None else usage
        usage = None if usage == "missing" else usage

        def factory(config, provider, model_name, settings):
            return _FakeEssayGrader(config, provider, model_name, settings, result, usage, error)

        g = InProcessGrader(model="m/x", settings=self.settings, grader_factory=factory, **kwargs)
        if prepare:
            g.prepare_namespace("ns", docs, Path(self._tmp.name))
        return g

    def test_setup_builds_isolated_config_and_ingests_materials(self):
        g = self._grader()
        vs = g._config["vectorstore"]
        self.assertEqual((str(Path(self._tmp.name) / "chroma"), "persistent", "eval"),
                         (vs["persist_directory"], vs["client_mode"], vs["collection_name"]))
        self.assertNotEqual(vs["persist_directory"], self.settings.raw["vectorstore"]["persist_directory"])
        paths, course_id = g._grader.ingested[0]
        self.assertEqual("eval:ns", course_id)
        self.assertEqual(sorted(d.source for d in DOCS), sorted(p.name for p in paths))
        self.assertEqual(("openrouter", "m/x"), (g._grader.provider, g._grader.model_name))

    def test_grader_is_built_once_across_namespaces(self):
        g = self._grader()
        first = g._grader
        g.prepare_namespace("ns2", DOCS, Path(self._tmp.name))
        self.assertIs(first, g._grader)
        self.assertEqual(["eval:ns", "eval:ns2"], [c for _, c in first.ingested])

    def test_success_maps_score_sources_tokens_and_citations(self):
        g = self._grader()
        raw = g.grade("ns", ITEM, REQ)
        self.assertTrue(raw.success)
        self.assertIsNone(raw.error_type)
        self.assertEqual((80.0, 0.9), (raw.score, raw.confidence))
        self.assertEqual([source_name("q1"), source_name("q2")], raw.retrieved_sources)
        self.assertEqual((1200, 150, False), (raw.prompt_tokens, raw.completion_tokens,
                                              raw.tokens_estimated))
        self.assertEqual((1, 2), (raw.citations_kept, raw.citations_dropped))
        self.assertEqual("openrouter-upstream", raw.provider)
        call = g._grader.calls[0]
        self.assertEqual(("eval:ns", "en", {"criteria": {}}),
                         (call["course_id"], call["language"], call["rubric"]))

    def test_provider_falls_back_to_wrapper_then_configured(self):
        g = self._grader()
        g._grader.rag_pipeline.llm.served = None
        self.assertEqual("openrouter", g.grade("ns", ITEM, REQ).provider)

    def test_parse_failure_is_not_a_zero_score(self):
        g = self._grader(result={"score": 0, "error": "Failed to parse structured LLM response",
                                 "confidence": 0.0})
        raw = g.grade("ns", ITEM, REQ)
        self.assertEqual(("parse_failure", None, False), (raw.error_type, raw.score, raw.success))

    def test_no_materials(self):
        g = self._grader(result={"success": False, "score": 0,
                                 "error": "No relevant materials retrieved"})
        raw = g.grade("ns", ITEM, REQ)
        self.assertEqual(("no_materials", None, False), (raw.error_type, raw.score, raw.success))

    def test_rate_limit_error_text_is_transient(self):
        for text in ("All LLM providers failed. Last error: 429 Too Many Requests",
                     "Rate limit reached", "Error code: 503 Service Unavailable",
                     "Request timed out", "timeout"):
            g = self._grader(result={"score": 0, "error": text})
            with self.assertRaises(TransientGraderError, msg=text):
                g.grade("ns", ITEM, REQ)

    def test_transient_exception_from_grade_essay(self):
        g = self._grader(error=RuntimeError("502 Bad Gateway"))
        with self.assertRaises(TransientGraderError):
            g.grade("ns", ITEM, REQ)

    def test_other_errors_are_provider_errors(self):
        g = self._grader(result={"score": 0, "error": "invalid api key"})
        raw = g.grade("ns", ITEM, REQ)
        self.assertEqual(("provider_error", None, False), (raw.error_type, raw.score, raw.success))
        g = self._grader(error=RuntimeError("boom"))
        raw = g.grade("ns", ITEM, REQ)
        self.assertEqual(("provider_error", None, False), (raw.error_type, raw.score, raw.success))

    def test_usage_missing_marks_estimated(self):
        g = self._grader(usage="missing")
        raw = g.grade("ns", ITEM, REQ)
        self.assertTrue(raw.tokens_estimated)
        self.assertEqual((100, 20), (raw.prompt_tokens, raw.completion_tokens))

    def test_temperature_override_reaches_config(self):
        g = self._grader(temperature=0.0)
        self.assertEqual(0.0, g._config["llm"]["temperature"])
        self.assertEqual(0.0, g._grader.config["llm"]["temperature"])

    def test_temperature_defaults_to_settings(self):
        g = self._grader()
        self.assertEqual(self.settings.raw["llm"]["temperature"], g._config["llm"]["temperature"])

    def test_rag_mode_keeps_product_retriever(self):
        g = self._grader()
        self.assertIsInstance(g._grader.rag_pipeline.retriever, _ProductRetriever)

    def test_oracle_supplies_only_gold_document(self):
        g = self._grader(context_mode="oracle")
        g.grade("ns", ITEM, REQ)
        docs = g._grader.last_docs
        self.assertEqual([gold_source(ITEM)], [d.metadata["source"] for d in docs])
        self.assertEqual(GOLD_TEXT, docs[0].page_content)
        self.assertEqual("N/A", docs[0].metadata["page"])
        docs = g._grader.rag_pipeline.retriever.retrieve("anything")
        self.assertEqual([gold_source(ITEM)], [d.metadata["source"] for d in docs])

    def test_oracle_is_per_thread(self):
        g = self._grader(context_mode="oracle")
        seen = {}
        barrier = threading.Barrier(2)

        def run(item):
            barrier.wait()
            for _ in range(50):
                g.grade("ns", item, GradeRequest(item.question, "x", "en"))
                seen.setdefault(item.item_id, set()).add(
                    g._grader.rag_pipeline.retriever.retrieve("q")[0].metadata["source"])

        threads = [threading.Thread(target=run, args=(i,)) for i in (ITEM, OTHER)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual({"i1": {gold_source(ITEM)}, "i2": {gold_source(OTHER)}}, seen)

    def test_oracle_rejects_pdf_references(self):
        with self.assertRaises(ValueError) as ctx:
            self._grader(context_mode="oracle", docs=[MaterialDoc("case.pdf", "", "/x/case.pdf")])
        self.assertIn("oracle mode needs text references", str(ctx.exception))

    def test_no_context_supplies_placeholder(self):
        g = self._grader(context_mode="no_context")
        g.grade("ns", ITEM, REQ)
        docs = g._grader.last_docs
        self.assertEqual(["none"], [d.metadata["source"] for d in docs])
        self.assertEqual("(No course materials are available for this question.)",
                         docs[0].page_content)

    def test_unknown_context_mode_rejected(self):
        with self.assertRaises(ValueError):
            self._grader(context_mode="bogus", prepare=False)

    def test_grade_before_prepare_raises(self):
        g = self._grader(prepare=False)
        with self.assertRaises(RuntimeError):
            g.grade("ns", ITEM, REQ)

    def test_build_grader_inprocess(self):
        g = build_grader("inprocess", model="m/x", settings=self.settings,
                         grader_factory=lambda *a, **k: None)
        self.assertIsInstance(g, InProcessGrader)
        self.assertEqual("inprocess", g.name)


if __name__ == "__main__":
    unittest.main()
