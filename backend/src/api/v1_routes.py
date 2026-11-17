"""Generic LMS-agnostic /v1/ endpoints for namespace-isolated RAG autograding."""

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Path as PathParam, UploadFile
from loguru import logger

from ..vectorstore.filters import build_chroma_where_filter
from .locking import LockAcquisitionError
from .request_utils import normalize_grade, optional_page, safe_filename, save_upload, validate_material_filename
from .v1_models import (
    V1Citation,
    V1CriterionScore,
    V1DeleteResponse,
    V1GradeRequest,
    V1GradeResponse,
    V1NamespaceInfoResponse,
    V1RetrievedDoc,
    V1UploadResponse,
)

router = APIRouter(prefix="/v1", tags=["Generic Autograder API v1"])
NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def get_grader():
    """Return the shared EssayGrader instance from the main FastAPI app."""
    from .app import grader
    return grader


def get_operation_lock(namespace: str, write: bool = False):
    """Acquire a namespace-scoped read or write lock."""
    from .app import operation_locks
    resource = f"namespace:{namespace}"
    return operation_locks.write(resource) if write else operation_locks.read(resource)


def _validate_namespace(namespace: str) -> str:
    cleaned = (namespace or "").strip()
    if not NAMESPACE_PATTERN.fullmatch(cleaned):
        raise HTTPException(
            status_code=400,
            detail="Invalid namespace. Use 1-128 alphanumeric, '.', '_', or '-' characters.",
        )
    return cleaned


def _namespace_upload_dir(data_dir: Path, namespace: str) -> Path:
    digest = hashlib.sha1(namespace.encode("utf-8")).hexdigest()[:8]
    safe_prefix = re.sub(r"[^A-Za-z0-9_-]", "_", namespace)[:40].strip("_") or "ns"
    return data_dir / "uploads" / f"ns_{safe_prefix}_{digest}"


def _parse_tags_json(raw_tags: str) -> Dict[str, Any]:
    if not raw_tags or not raw_tags.strip():
        return {}
    try:
        parsed = json.loads(raw_tags)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid tags JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="tags must be a JSON object")
    return parsed


@router.post("/namespaces/{namespace}/materials", response_model=V1UploadResponse)
def upload_namespace_material(
    namespace: str = PathParam(...),
    file: UploadFile = File(...),
    module: Optional[str] = Form(default=None),
    tags: str = Form(default=""),
):
    """Upload and index a material file into an isolated namespace with optional module/tags."""
    ns = _validate_namespace(namespace)
    filename = validate_material_filename(file.filename)
    parsed_tags = _parse_tags_json(tags)

    try:
        grader = get_grader()
        with get_operation_lock(ns, write=True):
            from ..utils import DATA_DIR

            upload_dir = _namespace_upload_dir(DATA_DIR, ns)
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / filename
            save_upload(file, file_path)

            result = grader.ingest_course_materials(
                [file_path],
                course_id=ns,
                module=module,
                tags=parsed_tags,
            )

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "Ingestion failed"))

        return V1UploadResponse(
            success=True,
            message=f"Successfully indexed {filename}",
            namespace=ns,
            filename=filename,
            module=module,
            tags=parsed_tags,
            chunk_count=int(result.get("chunks_created", 0)),
            documents_loaded=int(result.get("documents_loaded", 0)),
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/namespaces/{namespace}/materials", response_model=V1NamespaceInfoResponse)
def get_namespace_materials(namespace: str = PathParam(...)):
    """Inspect indexed chunk count and uploaded filenames for a namespace."""
    ns = _validate_namespace(namespace)
    try:
        grader = get_grader()
        with get_operation_lock(ns, write=False):
            vs_info = grader.rag_pipeline.get_vectorstore_info(ns)
            from ..utils import DATA_DIR

            upload_dir = _namespace_upload_dir(DATA_DIR, ns)
            files = sorted(f.name for f in upload_dir.iterdir() if f.is_file()) if upload_dir.exists() else []

        return V1NamespaceInfoResponse(
            success=True,
            namespace=ns,
            collection_name=vs_info.get("collection_name", ""),
            document_count=int(vs_info.get("document_count", 0)),
            uploaded_files=files,
            embedding_model=getattr(grader.rag_pipeline, "current_embedding_model", ""),
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/namespaces/{namespace}/materials/{filename}", response_model=V1DeleteResponse)
def delete_namespace_material_file(
    namespace: str = PathParam(...),
    filename: str = PathParam(...),
):
    """Remove a single uploaded file and its vector chunks from a namespace."""
    ns = _validate_namespace(namespace)
    clean_name = safe_filename(filename)
    try:
        grader = get_grader()
        with get_operation_lock(ns, write=True):
            deleted = grader.delete_course_material_file(ns, clean_name)
            from ..utils import DATA_DIR

            file_path = _namespace_upload_dir(DATA_DIR, ns) / clean_name
            if file_path.exists():
                file_path.unlink()

        return V1DeleteResponse(
            success=bool(deleted),
            message=f"Deleted '{clean_name}'" if deleted else f"No vectors found for '{clean_name}'",
            namespace=ns,
            filename=clean_name,
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/namespaces/{namespace}", response_model=V1DeleteResponse)
def clear_namespace(namespace: str = PathParam(...)):
    """Delete all vectors and uploaded files for a namespace."""
    ns = _validate_namespace(namespace)
    try:
        grader = get_grader()
        with get_operation_lock(ns, write=True):
            grader.clear_vector_store(ns)
            from ..utils import DATA_DIR

            upload_dir = _namespace_upload_dir(DATA_DIR, ns)
            if upload_dir.exists():
                shutil.rmtree(upload_dir)

        return V1DeleteResponse(
            success=True,
            message=f"Cleared namespace '{ns}'",
            namespace=ns,
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/namespaces/{namespace}/grade", response_model=V1GradeResponse)
def grade_in_namespace(
    request: V1GradeRequest,
    namespace: str = PathParam(...),
):
    """Grade one student answer against scoped materials in a namespace."""
    ns = _validate_namespace(namespace)
    if not request.question.strip() or not request.essay.strip():
        raise HTTPException(status_code=400, detail="Question and essay must be non-empty")

    where_filter = None
    if request.material_filter is not None:
        where_filter = build_chroma_where_filter(
            modules=request.material_filter.modules,
            sources=request.material_filter.sources,
            tags=request.material_filter.tags,
        )

    try:
        grader = get_grader()
        rubric = request.rubric if request.rubric else {"criteria": {}}
        with get_operation_lock(ns, write=False):
            result = grader.grade_essay(
                question=request.question,
                essay=request.essay,
                rubric=rubric,
                course_id=ns,
                metadata_filter=where_filter,
            )

        if not result.get("success", True) and result.get("error"):
            return V1GradeResponse(
                success=False,
                namespace=ns,
                score=0.0,
                feedback=str(result.get("feedback", "Grading failed")),
                error=str(result.get("error")),
            )

        scaled_score, normalized_criteria, confidence = normalize_grade(
            result=result,
            rubric=rubric,
            maximum_grade=request.maximum_grade,
        )
        logger.info(f"v1 grading complete namespace={ns} score={scaled_score:.1f}/{request.maximum_grade}")

        return V1GradeResponse(
            success=True,
            namespace=ns,
            score=scaled_score,
            feedback=str(result.get("feedback", "")),
            criterion_scores={name: V1CriterionScore(**data) for name, data in normalized_criteria.items()},
            citations=[
                V1Citation(
                    text=str(c.get("text", "")),
                    source=str(c.get("source", "Unknown")),
                    page=optional_page(c.get("page")),
                )
                for c in (result.get("citations") or [])
                if isinstance(c, dict)
            ],
            confidence=confidence,
            retrieved_documents=[
                V1RetrievedDoc(
                    content=str(d.get("content", "")),
                    source=str(d.get("source", "Unknown")),
                    page=d.get("page"),
                )
                for d in (result.get("retrieved_documents") or [])
                if isinstance(d, dict)
            ],
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
