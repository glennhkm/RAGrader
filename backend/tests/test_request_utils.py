"""Unit tests for Moodle request normalization helpers."""

import unittest

from fastapi import HTTPException

from src.api.request_utils import normalize_grade, rubric_maxima, safe_filename


class RequestUtilsTest(unittest.TestCase):
    def test_safe_filename_removes_path_components(self):
        self.assertEqual("material.pdf", safe_filename("../../material.pdf"))
        self.assertEqual("material.pdf", safe_filename(r"C:\\fakepath\\material.pdf"))

    def test_safe_filename_rejects_empty_name(self):
        with self.assertRaises(HTTPException):
            safe_filename("")

    def test_extracts_both_plugin_rubric_formats(self):
        self.assertEqual(
            {"Accuracy": 40.0},
            rubric_maxima({"Accuracy": {"max_score": 40}}),
        )
        self.assertEqual(
            {"Accuracy": 25.0},
            rubric_maxima({"criteria": {"Accuracy": {"points": 25}}}),
        )

    def test_complete_criterion_scores_drive_scaled_grade(self):
        result = {
            "score": 5,
            "criterion_scores": {
                "Accuracy": {"score": 30, "feedback": "Good"},
                "Evidence": {"score": 10, "feedback": "Partial"},
            },
            "confidence": 80,
        }
        rubric = {
            "Accuracy": {"max_score": 40},
            "Evidence": {"max_score": 20},
        }

        score, criteria, confidence = normalize_grade(result, rubric, 50)

        self.assertEqual(33.33, score)
        self.assertEqual(30.0, criteria["Accuracy"]["score"])
        self.assertEqual(0.8, confidence)

    def test_simple_grading_uses_percentage(self):
        score, criteria, confidence = normalize_grade(
            {"score": 75, "criterion_scores": {}, "confidence": 1.5},
            {},
            40,
        )
        self.assertEqual(30.0, score)
        self.assertEqual({}, criteria)
        self.assertEqual(0.015, confidence)


if __name__ == "__main__":
    unittest.main()
