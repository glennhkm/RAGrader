"""Command-line client for the generic /v1 autograding API.

Usage (from ``backend/``)::

    python -m src.cli ingest    --namespace cs101 --module week-1 materials/week-1.txt
    python -m src.cli grade     --namespace cs101 --question "..." --answer "..." --module week-1
    python -m src.cli grade-csv --namespace cs101 --input answers.csv --output graded.csv \\
        --module week-1 --module week-2 --module week-3 [--tag topic=routing]

Only ``requirements-cli.txt`` is needed to run the CLI against a remote API.

The CLI talks to a running API over HTTP (``--api-url`` / ``RAG_API_URL``,
``--token`` / ``RAG_API_TOKEN``), so it uses exactly the same validation,
locking, authentication and grading path as any other client.
"""

import argparse
import csv
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx

SUPPORTED_EXTENSIONS = (".pdf", ".pptx", ".docx", ".txt")
RESULT_COLUMNS = (
    "score", "max_grade", "confidence", "needs_review", "language", "feedback", "citations",
    "integrity_warnings", "error",
)
EXIT_OK, EXIT_USAGE, EXIT_PARTIAL = 0, 1, 2


class ApiError(RuntimeError):
    """The API rejected a request or could not be reached."""


class RagApiClient:
    """Thin synchronous client for ``/v1/namespaces/{namespace}/*``."""

    def __init__(self, api_url: str, token: str = "", timeout: float = 300.0,
                 http_client: Optional[httpx.Client] = None):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = http_client or httpx.Client(timeout=timeout)
        self._base = api_url.rstrip("/")
        self._headers = headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        headers = dict(self._headers)
        headers["X-Request-ID"] = uuid.uuid4().hex
        try:
            response = self._http.request(method, f"{self._base}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"Cannot reach the API at {self._base}: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(f"HTTP {response.status_code}: {detail}")
        return response.json()

    def upload(self, namespace: str, path: Path, module: Optional[str] = None,
               topic: Optional[str] = None, tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        data: Dict[str, str] = {}
        if module:
            data["module"] = module
        if topic:
            data["topic"] = topic
        if tags:
            data["tags"] = json.dumps(tags)
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, "application/octet-stream")}
            return self._request("POST", f"/v1/namespaces/{namespace}/materials", data=data, files=files)

    def grade(self, namespace: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/v1/namespaces/{namespace}/grade", json=payload)


def _parse_tags(pairs: Sequence[str]) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"--tag must look like key=value, got {pair!r}")
        tags[key.strip()] = value.strip()
    return tags


def _material_files(paths: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"No such file or directory: {raw}")
    return files


def _grade_payload(args: argparse.Namespace, question: str, answer: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"question": question, "essay": answer, "maximum_grade": args.max_grade}
    if args.rubric:
        payload["rubric"] = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
    material_filter = {key: value for key, value in (
        ("modules", args.module or []),
        ("sources", args.source or []),
        ("tags", _parse_tags(args.tag)),
    ) if value}
    if material_filter:
        payload["material_filter"] = material_filter
    if args.language:
        payload["language"] = args.language
    return payload


def _format_citations(citations: Sequence[Dict[str, Any]]) -> str:
    parts = []
    for citation in citations or []:
        source = citation.get("source") or "Unknown"
        page = citation.get("page")
        parts.append(f"{source}#{page}" if page else str(source))
    return "; ".join(parts)


def cmd_ingest(client: RagApiClient, args: argparse.Namespace) -> int:
    tags = _parse_tags(args.tag)
    files = _material_files(args.paths)
    if not files:
        print("No supported files found (.pdf, .pptx, .docx, .txt)", file=sys.stderr)
        return EXIT_USAGE
    failures = 0
    for path in files:
        try:
            result = client.upload(args.namespace, path, module=args.module, topic=args.topic, tags=tags)
            print(f"OK   {path.name}: {result.get('chunk_count', 0)} chunks"
                  + (f" (module={result.get('module')})" if result.get("module") else ""))
        except (ApiError, OSError) as exc:
            failures += 1
            print(f"FAIL {path.name}: {exc}", file=sys.stderr)
    return EXIT_PARTIAL if failures else EXIT_OK


def cmd_grade(client: RagApiClient, args: argparse.Namespace) -> int:
    result = client.grade(args.namespace, _grade_payload(args, args.question, args.answer))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return EXIT_OK if result.get("success", False) else EXIT_PARTIAL


def _grade_row(client: RagApiClient, args: argparse.Namespace, row: Dict[str, str]) -> Dict[str, Any]:
    question = (row.get("question") or args.question or "").strip()
    answer = (row.get("answer") or row.get("essay") or "").strip()
    out: Dict[str, Any] = dict(row)
    out.update({column: "" for column in RESULT_COLUMNS})
    out["max_grade"] = args.max_grade
    if not question or not answer:
        out.update(error="missing question or answer", needs_review=True)
        return out
    try:
        result = client.grade(args.namespace, _grade_payload(args, question, answer))
    except ApiError as exc:
        out.update(error=str(exc), needs_review=True)
        return out
    confidence = float(result.get("confidence") or 0.0)
    failed = not result.get("success", False)
    warnings = [str(w) for w in (result.get("integrity_warnings") or [])]
    out.update(
        score=result.get("score", 0.0),
        confidence=round(confidence, 4),
        needs_review=failed or bool(warnings) or confidence < args.review_threshold,
        language=result.get("language") or "",
        feedback=result.get("feedback", ""),
        citations=_format_citations(result.get("citations") or []),
        integrity_warnings="; ".join(warnings),
        error=(result.get("error") or "grading failed") if failed else "",
    )
    return out


def cmd_grade_csv(client: RagApiClient, args: argparse.Namespace) -> int:
    _parse_tags(args.tag)  # fail fast on malformed --tag before sending any request
    with open(args.input, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        input_columns = list(reader.fieldnames or [])
    if "answer" not in input_columns and "essay" not in input_columns:
        print("Input CSV needs an 'answer' (or 'essay') column", file=sys.stderr)
        return EXIT_USAGE
    if "question" not in input_columns and not args.question:
        print("Provide a 'question' column or --question", file=sys.stderr)
        return EXIT_USAGE

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        results = list(pool.map(lambda row: _grade_row(client, args, row), rows))

    columns = input_columns + [c for c in RESULT_COLUMNS if c not in input_columns]
    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    failed = sum(1 for r in results if r.get("error"))
    review = sum(1 for r in results if r.get("needs_review"))
    print(f"Graded {len(results) - failed}/{len(results)} rows ({review} flagged for review) -> {args.output}")
    return EXIT_PARTIAL if failed else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.cli", description=__doc__.split("\n\n")[0])
    parser.add_argument("--api-url", default=None, help="API base URL (default: RAG_API_URL or http://127.0.0.1:8000)")
    parser.add_argument("--token", default=None, help="Bearer token (default: RAG_API_TOKEN or API_AUTH_TOKEN)")
    parser.add_argument("--timeout", type=float, default=300.0, help="Per-request timeout in seconds")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Upload material files or folders into a namespace")
    ingest.add_argument("--namespace", required=True)
    ingest.add_argument("--module", help="Module/week tag stored on every chunk (e.g. week-1)")
    ingest.add_argument("--topic")
    ingest.add_argument("--tag", action="append", default=[], help="Extra key=value tag (repeatable)")
    ingest.add_argument("paths", nargs="+")

    def add_grading_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--namespace", required=True)
        p.add_argument("--rubric", help="Path to a rubric JSON file")
        p.add_argument("--max-grade", type=float, default=100.0)
        p.add_argument("--module", action="append", help="Restrict retrieval to this module (repeatable)")
        p.add_argument("--source", action="append", help="Restrict retrieval to this filename (repeatable)")
        p.add_argument("--tag", action="append", default=[],
                       help="Restrict retrieval to chunks ingested with this key=value tag (repeatable)")
        p.add_argument("--language", choices=("auto", "en", "id"))

    grade = sub.add_parser("grade", help="Grade one answer")
    add_grading_options(grade)
    grade.add_argument("--question", required=True)
    grade.add_argument("--answer", required=True)

    grade_csv = sub.add_parser("grade-csv", help="Grade every row of a CSV (question, answer columns)")
    add_grading_options(grade_csv)
    grade_csv.add_argument("--input", required=True)
    grade_csv.add_argument("--output", required=True)
    grade_csv.add_argument("--question", help="Question used when the CSV has no 'question' column")
    grade_csv.add_argument("--concurrency", type=int, default=4)
    grade_csv.add_argument("--review-threshold", type=float, default=0.6,
                           help="Flag rows whose confidence is below this value")
    return parser


def main(argv: Optional[Sequence[str]] = None, http_client: Optional[httpx.Client] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.api_url is None or args.token is None:
        from .utils.config import get_settings

        client_settings = get_settings().client
        args.api_url = args.api_url or client_settings.api_url
        args.token = client_settings.api_token if args.token is None else args.token
    client = RagApiClient(args.api_url, args.token, timeout=args.timeout, http_client=http_client)
    commands = {"ingest": cmd_ingest, "grade": cmd_grade, "grade-csv": cmd_grade_csv}
    try:
        return commands[args.command](client, args)
    except (ApiError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
