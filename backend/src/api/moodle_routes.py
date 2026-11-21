"""Moodle-compatible API endpoints for RAG Essay Grading System.

This module provides endpoints that are compatible with the Moodle
local_assign_ai_rag plugin, enabling seamless integration between
Moodle's assignment grading system and the RAG pipeline.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Path as PathParameter
from typing import List, Optional
import shutil
from loguru import logger

from .moodle_models import (
    MoodleAssignRequest,
    MoodleAssignResponse,
    MoodleUploadResponse,
    MoodleCollectionResponse,
    MoodleStatusResponse,
    MoodleCriterionScore,
    MoodleCitation,
    MoodleRetrievedDoc,
)
from .request_utils import (
    API_VERSION,
    normalize_grade,
    optional_page,
    safe_filename,
    save_upload,
    validate_material_filename,
)
from .locking import LockAcquisitionError
from .runtime import get_runtime
from ..rag.prompts import normalize_language
from ..vectorstore.embeddings import EmbeddingMismatchError
from ..vectorstore.filters import (
    EmptyScopeFilterError,
    _slugify,
    build_explicit_scope_filter,
    is_valid_material_id,
)

def _clean_material_id(material_id):
    """Return a validated owner id, ``None`` when absent/blank, else HTTP 400."""
    # Non-str covers an unresolved FastAPI default when a route is called directly.
    if not isinstance(material_id, str) or not material_id.strip():
        return None
    material_id = material_id.strip()
    if not is_valid_material_id(material_id):
        raise HTTPException(
            status_code=400,
            detail="material_id must match ^[a-z_]+:[0-9]+$ (e.g. airagmaterial:12)",
        )
    return material_id


def _material_upload_dir(course_id, material_id):
    from ..utils import DATA_DIR
    base = DATA_DIR / "uploads" / f"course_{course_id}"
    return base / _slugify(material_id) if material_id else base


# Router for Moodle endpoints
router = APIRouter(prefix="", tags=["Moodle Integration"])


def get_grader():
    """Get the grader of the running application."""
    return get_runtime().grader


def get_operation_lock(course_id: object = "default", write: bool = False):
    """Get a replica-safe read or write lock for one course."""
    operation_locks = get_runtime().operation_locks
    resource = f"course:{course_id}"
    return operation_locks.write(resource) if write else operation_locks.read(resource)


@router.post("/assign/answer", response_model=MoodleAssignResponse)
def moodle_grade_assignment(request: MoodleAssignRequest):
    """
    Grade a student's assignment submission using RAG pipeline.
    
    This endpoint is designed to be compatible with Moodle's local_assign_ai_rag
    plugin. It receives the assignment context, student submission, and rubric,
    then uses the RAG pipeline to generate a contextual grade and feedback.
    
    The grading process:
    1. Retrieves relevant course materials from the vector store
    2. Builds a context-aware prompt with question, essay, rubric, and materials
    3. Uses LLM to generate grading response
    4. Returns structured response with score, feedback, citations, and confidence
    
    Args:
        request: MoodleAssignRequest containing:
            - course_id: Moodle course ID (used for collection selection)
            - question: The assignment question/prompt
            - essay: Student's answer text
            - rubric: Grading rubric structure
            - maximum_grade: Maximum possible grade
            - Other metadata (student_name, userid, etc.)
    
    Returns:
        MoodleAssignResponse with:
            - success: Boolean indicating if grading succeeded
            - score: Numeric grade (scaled to maximum_grade)
            - feedback: Overall feedback text
            - criterion_scores: Per-criterion scores if rubric provided
            - citations: References to course materials used
            - confidence: Model's confidence in the grading (0-1)
            - retrieved_documents: Documents used for context
    
    Raises:
        HTTPException: On validation or processing errors
    """
    logger.info(f"Moodle grading request for course {request.course_id}, assignment {request.assignment_id}")
    
    try:
        grader = get_grader()
        
        # Validate inputs
        if not request.question or len(request.question.strip()) < 1:
            raise HTTPException(
                status_code=400,
                detail="Question/prompt cannot be empty or too short"
            )
        
        if not request.essay or len(request.essay.strip()) < 1:
            raise HTTPException(
                status_code=400,
                detail="Essay/answer cannot be empty or too short"
            )
        
        # Do not write student identity or answer content to application logs.
        logger.info(f"Question length: {len(request.question)}, Essay length: {len(request.essay)}")
        logger.info(f"Rubric provided: {bool(request.rubric)}")
        
        # Grade using RAG pipeline
        rubric = request.rubric if request.rubric else {"criteria": {}}
        metadata_filter = None
        if request.material_ids is not None:
            for owner in request.material_ids:
                if owner.strip() and not is_valid_material_id(owner.strip()):
                    raise HTTPException(
                        status_code=400,
                        detail="material_ids entries must match ^[a-z_]+:[0-9]+$",
                    )
        if (
            request.source_filter is not None
            or request.module_filter is not None
            or request.material_ids is not None
        ):
            # The plugin only sends a filter for linked materials; an explicit
            # but empty filter must not widen grading to the whole course.
            try:
                metadata_filter = build_explicit_scope_filter(
                    modules=request.module_filter,
                    sources=request.source_filter,
                    material_ids=(
                        [m.strip() for m in request.material_ids]
                        if request.material_ids is not None else None
                    ),
                )
            except EmptyScopeFilterError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "source_filter/module_filter/material_ids must contain at least one non-empty value; "
                        "omit them to grade against all course materials."
                    ),
                ) from exc
        # `lang` defaults to "en" in the request model, so only an explicitly
        # sent value may override PROMPT_LANGUAGE; otherwise existing Indonesian
        # Moodle classes would silently switch to English prompts.
        language = normalize_language(request.lang) if "lang" in request.model_fields_set else None
        with get_operation_lock(request.course_id):
            result = grader.grade_essay(
                question=request.question,
                essay=request.essay,
                rubric=rubric,
                course_id=str(request.course_id),
                metadata_filter=metadata_filter,
                language=language,
            )
        
        # Check for errors
        if not result.get('success', True) and result.get('error'):
            logger.warning(f"Grading returned error: {result.get('error')}")
            return MoodleAssignResponse(
                success=False,
                score=0,
                feedback=result.get('feedback', 'Error during grading'),
                error=result.get('error'),
                reply=result.get('feedback', 'Error during grading'),
                grade=None,
            )
        
        max_grade = request.maximum_grade
        scaled_score, normalized_criteria, confidence = normalize_grade(
            result=result,
            rubric=rubric,
            maximum_grade=max_grade,
        )

        criterion_scores = {}
        for name, data in normalized_criteria.items():
            criterion_scores[name] = MoodleCriterionScore(**data)
        
        # Process citations
        citations = []
        if result.get('citations'):
            for cite in result['citations']:
                if not isinstance(cite, dict):
                    continue
                citations.append(MoodleCitation(
                    text=str(cite.get('text', '')),
                    source=str(cite.get('source', 'Unknown')),
                    page=optional_page(cite.get('page'))
                ))
        
        # Process retrieved documents
        retrieved_docs = []
        if result.get('retrieved_documents'):
            for doc in result['retrieved_documents']:
                if not isinstance(doc, dict):
                    continue
                retrieved_docs.append(MoodleRetrievedDoc(
                    content=str(doc.get('content', '')),
                    source=str(doc.get('source', 'Unknown')),
                    page=doc.get('page')
                ))
        
        feedback = str(result.get('feedback', ''))
        
        logger.info(f"Grading complete. Score: {scaled_score:.1f}/{max_grade}, Confidence: {confidence:.2f}")
        
        return MoodleAssignResponse(
            success=True,
            score=scaled_score,
            feedback=feedback,
            criterion_scores=criterion_scores,
            citations=citations,
            confidence=confidence,
            retrieved_documents=retrieved_docs,
            language=result.get('language'),
            integrity_warnings=[str(w) for w in (result.get('integrity_warnings') or [])],
            # Legacy fields
            reply=feedback,
            grade=scaled_score,
            rubric_response=normalized_criteria
        )
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (HTTPException, EmbeddingMismatchError):
        raise
    except Exception as e:
        logger.error(f"Error in Moodle grading endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/moodle/upload", response_model=MoodleUploadResponse)
def moodle_upload_materials(
    files: List[UploadFile] = File(...),
    course_id: int = Form(..., gt=0),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
    moodle_site_id: str = Form("")
):
    """
    Upload course materials for a specific Moodle course.
    
    This endpoint allows uploading PDF and PPTX files to be ingested
    into the vector store for RAG-based grading.
    
    Args:
        files: List of PDF/PPTX files to upload
        course_id: Moodle course ID (used for collection naming)
        chunk_size: Size of text chunks (100-2000)
        chunk_overlap: Overlap between chunks (0-500)
        moodle_site_id: Identifier for the Moodle site
    
    Returns:
        MoodleUploadResponse with upload statistics
    """
    logger.info(f"Moodle upload request for course {course_id}: {len(files)} files")
    
    try:
        grader = get_grader()
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        # Validate files
        if not 100 <= chunk_size <= 2000:
            raise HTTPException(status_code=400, detail="chunk_size must be between 100 and 2000")
        if not 0 <= chunk_overlap <= 500 or chunk_overlap >= chunk_size:
            raise HTTPException(status_code=400, detail="chunk_overlap must be smaller than chunk_size")

        filenames = [validate_material_filename(file.filename) for file in files]
        
        # Save and ingest under one cross-replica course write lock.
        with get_operation_lock(course_id, write=True):
            from ..utils import DATA_DIR
            upload_dir = DATA_DIR / "uploads" / f"course_{course_id}"
            upload_dir.mkdir(parents=True, exist_ok=True)

            file_paths = []
            for file, filename in zip(files, filenames):
                file_path = upload_dir / filename
                save_upload(file, file_path)
                file_paths.append(file_path)
                logger.info(f"Saved file: {filename}")

            grader.update_chunking_config(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            result = grader.ingest_course_materials(file_paths, course_id=str(course_id))
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['message'])
        
        return MoodleUploadResponse(
            success=True,
            message=result['message'],
            course_id=course_id,
            documents_loaded=result.get('documents_loaded', 0),
            chunks_created=result.get('chunks_created', 0),
            total_documents_in_db=result.get('total_documents_in_db', 0),
            errors=result.get('errors', [])
        )
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (HTTPException, EmbeddingMismatchError):
        raise
    except Exception as e:
        logger.error(f"Error uploading materials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{course_id}", response_model=MoodleCollectionResponse)
def get_course_collection(course_id: int = PathParameter(..., gt=0)):
    """
    Get information about the collection for a specific course.
    
    Args:
        course_id: Moodle course ID
    
    Returns:
        Collection information including document count
    """
    try:
        grader = get_grader()
        
        # Get vectorstore info
        with get_operation_lock(course_id):
            vs_info = grader.rag_pipeline.get_vectorstore_info(str(course_id))
        
        return MoodleCollectionResponse(
            success=True,
            course_id=course_id,
            collection_name=vs_info.get('collection_name', 'default'),
            document_count=vs_info.get('document_count', 0),
            embedding_model=grader.rag_pipeline.current_embedding_model
        )
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting collection info: {e}")
        return MoodleCollectionResponse(
            success=False,
            course_id=course_id,
            collection_name="",
            document_count=0,
            embedding_model=""
        )


@router.delete("/collections/{course_id}")
def clear_course_collection(course_id: int = PathParameter(..., gt=0)):
    """
    Clear the collection for a specific course.
    
    Clears the Chroma collection and the uploaded files belonging to the
    requested course, so no course material is retained on disk after the
    collection is gone (same behavior as POST /course/materials/clear).
    
    Args:
        course_id: Moodle course ID
    
    Returns:
        Success status
    """
    try:
        grader = get_grader()
        with get_operation_lock(course_id, write=True):
            grader.clear_vector_store(str(course_id))

            from ..utils import DATA_DIR
            upload_dir = DATA_DIR / "uploads" / f"course_{course_id}"
            if upload_dir.exists():
                shutil.rmtree(upload_dir)
                logger.info(f"Cleared upload directory: {upload_dir}")
        
        return {
            "success": True,
            "message": f"Collection cleared for course {course_id}",
            "course_id": course_id
        }
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error clearing collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/moodle/status", response_model=MoodleStatusResponse)
def moodle_server_status():
    """
    Get RAG server status for Moodle health checks.
    
    Returns comprehensive status including vectorstore info,
    LLM configuration, and readiness state.
    """
    try:
        grader = get_grader()
        
        with get_operation_lock():
            vs_info = grader.rag_pipeline.get_vectorstore_info()
            llm_info = grader.rag_pipeline.get_llm_info()
            retrieval = grader.rag_pipeline.get_retriever_config()
        
        return MoodleStatusResponse(
            status="healthy",
            version=API_VERSION,
            vectorstore=vs_info,
            llm_info=llm_info,
            embedding_model=grader.rag_pipeline.current_embedding_model,
            retrieval=retrieval,
            ready=True
        )
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return MoodleStatusResponse(
            status="unhealthy",
            version=API_VERSION,
            ready=False
        )


# ============================================================================
# Course Materials Management Endpoints (for Moodle local_assign_ai_rag plugin)
# ============================================================================

@router.post("/course/materials/upload")
def upload_course_material(
    file: UploadFile = File(...),
    course_id: int = Form(..., gt=0),
    course_name: str = Form(""),
    material_id: Optional[str] = Form(None),
):
    """
    Upload a single course material file.
    
    This endpoint is used by the Moodle local_assign_ai_rag plugin
    to upload course materials (PDF, PPTX, DOCX, TXT) for ingestion
    into the RAG knowledge base.
    
    Args:
        file: The file to upload
        course_id: Moodle course ID
        course_name: Moodle course name (optional)
    
    Returns:
        Success status with chunk count
    """
    try:
        grader = get_grader()
        owner = _clean_material_id(material_id)
        
        filename = validate_material_filename(file.filename)
        logger.info(f"Course material upload for course {course_id}: {filename}")
        
        # Keep the file and its vectors consistent across every replica.
        with get_operation_lock(course_id, write=True):
            upload_dir = _material_upload_dir(course_id, owner)
            upload_dir.mkdir(parents=True, exist_ok=True)

            file_path = upload_dir / filename
            save_upload(file, file_path)
            logger.info(f"Saved file: {file_path}")

            ingest_kwargs = {"material_id": owner} if owner else {}
            result = grader.ingest_course_materials(
                [file_path], course_id=str(course_id), **ingest_kwargs
            )
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['message'])
        
        return {
            "success": True,
            "message": f"Successfully uploaded and processed {filename}",
            "filename": filename,
            "course_id": course_id,
            "chunk_count": result.get('chunks_created', 0),
            "documents_loaded": result.get('documents_loaded', 0)
        }
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (HTTPException, EmbeddingMismatchError):
        raise
    except Exception as e:
        logger.error(f"Error uploading course material: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/course/materials/clear")
def clear_course_materials(course_id: int = Form(..., gt=0)):
    """
    Clear all materials for a specific course from the knowledge base.
    
    Clears only the Chroma collection and uploads belonging to the course.
    
    Args:
        course_id: Moodle course ID
    
    Returns:
        Success status
    """
    logger.info(f"Clearing course materials for course {course_id}")
    
    try:
        grader = get_grader()
        with get_operation_lock(course_id, write=True):
            grader.clear_vector_store(str(course_id))

            # Also clear uploaded files for this course while writes are blocked.
            from ..utils import DATA_DIR
            upload_dir = DATA_DIR / "uploads" / f"course_{course_id}"
            if upload_dir.exists():
                shutil.rmtree(upload_dir)
                logger.info(f"Cleared upload directory: {upload_dir}")
        
        return {
            "success": True,
            "message": f"Successfully cleared materials for course {course_id}",
            "course_id": course_id
        }
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error clearing course materials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/course/materials/file")
def delete_course_material_file(
    course_id: int = Form(..., gt=0),
    filename: str = Form(...),
    material_id: Optional[str] = Form(None),
):
    """
    Delete a single course material file and its vector chunks.
    """
    try:
        filename = safe_filename(filename)
        owner = _clean_material_id(material_id)
        logger.info(f"Moodle delete request for file '{filename}' in course {course_id}")
        grader = get_grader()
        with get_operation_lock(course_id, write=True):
            delete_kwargs = {"material_id": owner} if owner else {}
            success = grader.delete_course_material_file(
                str(course_id), filename, **delete_kwargs
            )

            # Also clean up the saved file while writes are blocked.
            file_path = _material_upload_dir(course_id, owner) / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Removed file from disk: {file_path}")
            
        return {
            "success": success,
            "message": f"Successfully deleted vectors for '{filename}'" if success else f"No vectors found for '{filename}'",
            "course_id": course_id,
            "filename": filename
        }
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting course material file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/course/materials/status/{course_id}")
def get_course_materials_status(course_id: int = PathParameter(..., gt=0)):
    """
    Get the status of course materials in the knowledge base.
    
    Args:
        course_id: Moodle course ID
    
    Returns:
        Material statistics
    """
    try:
        grader = get_grader()
        with get_operation_lock(course_id):
            vs_info = grader.rag_pipeline.get_vectorstore_info(str(course_id))

            # Read file status from the same consistent course snapshot.
            from ..utils import DATA_DIR
            upload_dir = DATA_DIR / "uploads" / f"course_{course_id}"
            uploaded_files = []
            if upload_dir.exists():
                # Owned uploads live in per-material subdirectories; list those
                # files too, de-duplicated by name.
                uploaded_files = sorted({
                    f.name
                    for f in upload_dir.iterdir()
                    if f.is_file()
                } | {
                    f.name
                    for sub in upload_dir.iterdir() if sub.is_dir()
                    for f in sub.iterdir() if f.is_file()
                })
        
        return {
            "success": True,
            "course_id": course_id,
            "document_count": vs_info.get('document_count', 0),
            "collection_name": vs_info.get('collection_name', 'default'),
            "uploaded_files": uploaded_files,
            "files_count": len(uploaded_files)
        }
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting course materials status: {e}")
        return {
            "success": False,
            "course_id": course_id,
            "error": str(e)
        }


@router.get("/assign/status")
def assign_server_status():
    """
    Simple health check endpoint for the assignment grading service.
    Used by aiprovider_rag to check if the server is available.
    """
    try:
        grader = get_grader()
        with get_operation_lock():
            vs_info = grader.rag_pipeline.get_vectorstore_info()
            llm_info = grader.rag_pipeline.get_llm_info()
        
        return {
            "status": "ok",
            "ready": True,
            "document_count": vs_info.get('document_count', 0),
            "llm_provider": llm_info.get('provider', 'unknown'),
            "llm_model": llm_info.get('model', 'unknown')
        }
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        return {
            "status": "error",
            "ready": False,
            "error": str(e)
        }
