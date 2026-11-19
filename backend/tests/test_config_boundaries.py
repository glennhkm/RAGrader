"""Architecture guard: runtime configuration is read only through src/utils/config.py."""

import ast
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
ALLOWED = {SRC_DIR / "utils" / "config.py"}


def _environment_accesses(path: Path):
    """Yield (line, snippet) for os.getenv / os.environ / getenv / dotenv usage."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os" and node.attr in {"getenv", "environ", "putenv", "unsetenv"}:
                yield node.lineno, f"os.{node.attr}"
        elif isinstance(node, ast.ImportFrom) and node.module in {"os", "dotenv"}:
            names = {alias.name for alias in node.names}
            if node.module == "dotenv" or names & {"getenv", "environ"}:
                yield node.lineno, f"from {node.module} import {', '.join(sorted(names))}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "dotenv":
                    yield node.lineno, "import dotenv"


class ConfigBoundaryTest(unittest.TestCase):
    def test_no_environment_reads_outside_config_module(self):
        offenders = []
        for path in sorted(SRC_DIR.rglob("*.py")):
            if path in ALLOWED:
                continue
            for line, snippet in _environment_accesses(path):
                offenders.append(f"{path.relative_to(SRC_DIR.parent)}:{line}: {snippet}")
        self.assertEqual(
            [],
            offenders,
            "Read configuration via src.utils.config.get_settings() instead of the environment",
        )


if __name__ == "__main__":
    unittest.main()
