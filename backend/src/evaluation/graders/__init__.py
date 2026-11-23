"""Graders for the evaluation harness."""

from src.evaluation.graders.base import Grader


def build_grader(mode: str, **kwargs) -> Grader:
    if mode == "stub":
        from src.evaluation.graders.stub import StubGrader

        return StubGrader()
    if mode == "inprocess":
        from src.evaluation.graders.inprocess import InProcessGrader

        return InProcessGrader(**kwargs)
    if mode == "http":
        from src.evaluation.graders.http import HttpGrader

        return HttpGrader(**kwargs)
    raise ValueError(f"unknown grader mode: {mode}")
