"""Dependency hygiene: requirements match what src/ actually imports.

- No dead packages in requirements.txt (Cycle 1 rule).
- Every third-party module imported by src/ is declared in requirements.txt,
  unless it is an optional extra that is imported lazily (inside a function)
  or guarded by ``try/except ImportError``.
- Every core requirement is either imported, or a documented runtime/indirect pin.
"""

import ast
import re
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BACKEND_DIR / "src"

# import name -> distribution name in requirements*.txt
IMPORT_TO_DIST = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pydantic": "pydantic",
    "loguru": "loguru",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "redis": "redis",
    "httpx": "httpx",
    "chromadb": "chromadb",
    "langchain_core": "langchain-core",
    "langchain_community": "langchain-community",
    "langchain_text_splitters": "langchain-text-splitters",
    "langchain_huggingface": "langchain-huggingface",
    "openai": "openai",
    "rank_bm25": "rank-bm25",
    "pptx": "python-pptx",
    "docx": "python-docx",
    "fitz": "pymupdf",
    "PIL": "pillow",
}
OPTIONAL_IMPORTS = {
    "pinecone": "requirements-optional.txt",
    "fastembed": "requirements-local.txt",
    "sentence_transformers": "requirements-local.txt",
    "llama_cpp": "requirements-local.txt",
}
# Core requirements that are not imported by src/ on purpose.
DOCUMENTED_INDIRECT = {
    "gunicorn",          # production server (Dockerfile CMD)
    "python-multipart",  # FastAPI form/file uploads
    "pypdf",             # PyPDFLoader backend (langchain-community)
    "huggingface-hub",   # langchain-huggingface backend
    "posthog",           # chromadb 0.6.x telemetry pin (<6.0)
    "langchain",         # langchain-community runtime dependency
}
DEAD_PACKAGES = ("nltk", "tiktoken", "pandas", "numpy", "langchain-groq", "pinecone", "pydantic-settings")


def _requirements(name: str) -> set:
    packages = set()
    for line in (BACKEND_DIR / name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        dist = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0]
        packages.add(dist.strip().lower())
    return packages


def _commented_requirements(name: str) -> set:
    packages = set()
    for line in (BACKEND_DIR / name).read_text(encoding="utf-8").splitlines():
        match = re.match(r"#\s*([A-Za-z0-9_.-]+)\s*[<>=]", line.strip())
        if match:
            packages.add(match.group(1).lower())
    return packages


def _imports():
    """Yield (path, top-level module, guarded) for absolute imports in src/."""
    for path in SRC_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            guarded = False
            current = node
            while current in parents:
                current = parents[current]
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Try)):
                    guarded = True
                    break
            for name in names:
                yield path, name.split(".")[0], guarded


class DependencyHygieneTest(unittest.TestCase):
    def test_requirements_exclude_dead_packages(self):
        core = _requirements("requirements.txt")
        for dead in DEAD_PACKAGES:
            self.assertNotIn(dead, core)
        self.assertIn("pinecone", _requirements("requirements-optional.txt"))

    def test_every_third_party_import_is_declared_or_optional_and_lazy(self):
        core = _requirements("requirements.txt")
        stdlib = set(sys.stdlib_module_names)
        problems = []
        for path, module, guarded in _imports():
            if module in stdlib or module == "src":
                continue
            rel = path.relative_to(BACKEND_DIR)
            if module in OPTIONAL_IMPORTS:
                if not guarded:
                    problems.append(f"{rel}: optional '{module}' must be imported lazily or in try/except")
                continue
            dist = IMPORT_TO_DIST.get(module)
            if dist is None:
                problems.append(f"{rel}: unmapped third-party import '{module}'")
            elif dist not in core:
                problems.append(f"{rel}: '{module}' needs '{dist}' in requirements.txt")
        self.assertEqual([], problems)

    def test_every_core_requirement_is_used_or_documented(self):
        imported = {IMPORT_TO_DIST[m] for _, m, _ in _imports() if m in IMPORT_TO_DIST}
        unused = _requirements("requirements.txt") - imported - DOCUMENTED_INDIRECT
        self.assertEqual(set(), unused)

    def test_optional_extras_are_listed_in_their_files(self):
        local = _requirements("requirements-local.txt") | _commented_requirements("requirements-local.txt")
        for dist in ("fastembed", "sentence-transformers", "llama-cpp-python"):
            self.assertIn(dist, local)

    def test_dockerfile_installs_optional_extras_behind_build_args(self):
        dockerfile = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG INSTALL_LOCAL_EXTRAS=false", dockerfile)
        self.assertIn("ARG INSTALL_OPTIONAL_EXTRAS=false", dockerfile)
        self.assertIn("requirements-local.txt", dockerfile)
        self.assertIn("requirements-optional.txt", dockerfile)


if __name__ == "__main__":
    unittest.main()
