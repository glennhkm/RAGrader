"""A parsed LLM response without a usable score must never be released as a grade of 0."""

import json
import unittest
from unittest.mock import MagicMock

from langchain_core.documents import Document

from src.grading.grader import EssayGrader
from src.rag.pipeline import RAGPipeline
from src.rag.prompt_builder import PromptBuilder

RUBRIC = {"criteria": {"accuracy": {"max_points": 60}, "clarity": {"max_points": 40}}}


def grade(payload, rubric=None):
    p = RAGPipeline.__new__(RAGPipeline)
    p.prompt_builder = PromptBuilder()
    p.retriever, p.llm, p.vectorstore = MagicMock(), MagicMock(), MagicMock()
    p.retriever.retrieve.return_value = [
        Document(page_content="Ice is less dense than water.", metadata={"source": "a.txt"})]
    p.llm.generate.return_value = json.dumps(payload)
    p.vectorstore.get_count.return_value = 1
    g = EssayGrader.__new__(EssayGrader)
    g.rag_pipeline = p
    return g.grade_essay("Why does ice float?", "It is less dense.", rubric or {"criteria": {}})


class MissingScoreTest(unittest.TestCase):
    def test_unusable_score_is_a_failed_grade(self):
        for extra in ({}, {"score": None}, {"score": "good"}, {"score": float("nan")},
                      {"score": True}, {"score": ""}):
            with self.subTest(extra=extra):
                r = grade({"feedback": "x", "confidence": 0.9, **extra})
                self.assertIs(False, r["success"])
                self.assertIn("Failed to parse", r["error"])
                self.assertEqual(0.0, r["confidence"])

    def test_numeric_scores_still_grade(self):
        for score in (0, 85, 85.5, "85"):
            with self.subTest(score=score):
                self.assertIs(True, grade({"score": score, "feedback": "x"})["success"])

    def test_complete_rubric_criteria_replace_the_overall_score(self):
        crit = {"Accuracy": {"score": 50}, "clarity": {"score": "30"}}
        self.assertIs(True, grade({"criterion_scores": crit, "feedback": "x"}, RUBRIC)["success"])

    def test_incomplete_or_unscored_criteria_do_not(self):
        for crit in ({"accuracy": {"score": 50}},
                     {"accuracy": {"score": 50}, "clarity": {"feedback": "ok"}}):
            with self.subTest(crit=crit):
                r = grade({"criterion_scores": crit, "feedback": "x"}, RUBRIC)
                self.assertIs(False, r["success"])

    def test_unscored_criterion_fails_even_with_an_overall_score(self):
        crit = {"accuracy": {"score": 50}, "clarity": {"feedback": "ok"}}
        r = grade({"score": 80, "criterion_scores": crit, "feedback": "x"}, RUBRIC)
        self.assertIs(False, r["success"])  # the API would count clarity as 0


if __name__ == "__main__":
    unittest.main()
