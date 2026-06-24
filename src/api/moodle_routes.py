"""Moodle-compatible API endpoints for RAG Essay Grading System.

This module provides endpoints that are compatible with the Moodle
local_assign_ai_rag plugin, enabling seamless integration between
Moodle's assignment grading system and the RAG pipeline.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Optional
from pathlib import Path
import shutil
from loguru import logger

from .moodle_models import (
    MoodleAssignRequest,
    MoodleAssignResponse,
    MoodleUploadRequest,
    MoodleUploadResponse,
    MoodleCollectionResponse,
    MoodleStatusResponse,
    MoodleCriterionScore,
    MoodleCitation,
    MoodleRetrievedDoc,
)

# Router for Moodle endpoints
router = APIRouter(prefix="", tags=["Moodle Integration"])


def get_grader():
    """Get the grader instance from main app."""
    from .app import grader
    return grader


def get_config():
    """Get config from main app."""
    from .app import config
    return config


@router.post("/assign/answer", response_model=MoodleAssignResponse)
async def moodle_grade_assignment(request: MoodleAssignRequest):
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
        
        # Log request details
        logger.info(f"Grading essay for student: {request.student_name} (userid: {request.userid})")
        logger.info(f"Question length: {len(request.question)}, Essay length: {len(request.essay)}")
        logger.info(f"Rubric provided: {bool(request.rubric)}")
        
        # TODO: Future enhancement - use course_id to select course-specific collection
        # For now, we use the default collection
        
        # Grade using RAG pipeline
        result = grader.grade_essay(
            question=request.question,
            essay=request.essay,
            rubric=request.rubric if request.rubric else {"criteria": []},
            course_id=str(request.course_id)
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
        
        # Scale score to maximum grade
        raw_score = result.get('score', 0)
        max_grade = request.maximum_grade or 100
        
        # Assuming RAG returns score out of 100, scale to max_grade
        scaled_score = (raw_score / 100.0) * max_grade if raw_score else 0
        
        # Process criterion scores
        criterion_scores = {}
        if result.get('criterion_scores'):
            for name, data in result['criterion_scores'].items():
                criterion_scores[name] = MoodleCriterionScore(
                    score=data.get('score', 0),
                    feedback=data.get('feedback', ''),
                    evidence=data.get('evidence')
                )
        
        # Process citations
        citations = []
        if result.get('citations'):
            for cite in result['citations']:
                citations.append(MoodleCitation(
                    text=cite.get('text', ''),
                    source=cite.get('source', 'Unknown'),
                    page=cite.get('page')
                ))
        
        # Process retrieved documents
        retrieved_docs = []
        if result.get('retrieved_documents'):
            for doc in result['retrieved_documents']:
                retrieved_docs.append(MoodleRetrievedDoc(
                    content=doc.get('content', ''),
                    source=doc.get('source', 'Unknown'),
                    page=doc.get('page')
                ))
        
        feedback = result.get('feedback', '')
        confidence = result.get('confidence', 0.0)
        
        logger.info(f"Grading complete. Score: {scaled_score:.1f}/{max_grade}, Confidence: {confidence:.2f}")
        
        return MoodleAssignResponse(
            success=True,
            score=round(scaled_score, 2),
            feedback=feedback,
            criterion_scores=criterion_scores,
            citations=citations,
            confidence=confidence,
            retrieved_documents=retrieved_docs,
            # Legacy fields
            reply=feedback,
            grade=round(scaled_score, 2),
            rubric_response=result.get('criterion_scores', {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Moodle grading endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/moodle/upload", response_model=MoodleUploadResponse)
async def moodle_upload_materials(
    files: List[UploadFile] = File(...),
    course_id: int = Form(...),
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
        config = get_config()
        
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        # Validate files
        valid_extensions = ['.pdf', '.pptx']
        for file in files:
            ext = Path(file.filename).suffix.lower()
            if ext not in valid_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type: {file.filename}. Only PDF and PPTX files are allowed."
                )
        
        # Update chunking config
        grader.update_chunking_config(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # Save uploaded files
        from ..utils import DATA_DIR
        upload_dir = DATA_DIR / "uploads" / f"course_{course_id}"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_paths = []
        for file in files:
            file_path = upload_dir / file.filename
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_paths.append(file_path)
            logger.info(f"Saved file: {file.filename}")
        
        # Ingest documents
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading materials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{course_id}", response_model=MoodleCollectionResponse)
async def get_course_collection(course_id: int):
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
        vs_info = grader.rag_pipeline.get_vectorstore_info(str(course_id))
        
        return MoodleCollectionResponse(
            success=True,
            course_id=course_id,
            collection_name=vs_info.get('collection_name', 'default'),
            document_count=vs_info.get('document_count', 0),
            embedding_model=grader.rag_pipeline.current_embedding_model
        )
        
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
async def clear_course_collection(course_id: int):
    """
    Clear the collection for a specific course.
    
    Note: Currently clears the entire vector store.
    Future enhancement: per-course collections.
    
    Args:
        course_id: Moodle course ID
    
    Returns:
        Success status
    """
    try:
        grader = get_grader()
        grader.clear_vector_store(str(course_id))
        
        return {
            "success": True,
            "message": f"Collection cleared for course {course_id}",
            "course_id": course_id
        }
        
    except Exception as e:
        logger.error(f"Error clearing collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/moodle/status", response_model=MoodleStatusResponse)
async def moodle_server_status():
    """
    Get RAG server status for Moodle health checks.
    
    Returns comprehensive status including vectorstore info,
    LLM configuration, and readiness state.
    """
    try:
        grader = get_grader()
        
        vs_info = grader.rag_pipeline.get_vectorstore_info()
        llm_info = grader.rag_pipeline.get_llm_info()
        
        return MoodleStatusResponse(
            status="healthy",
            version="1.0.0",
            vectorstore=vs_info,
            llm_info=llm_info,
            embedding_model=grader.rag_pipeline.current_embedding_model,
            ready=True
        )
        
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return MoodleStatusResponse(
            status="unhealthy",
            version="1.0.0",
            ready=False
        )


# ============================================================================
# Course Materials Management Endpoints (for Moodle local_assign_ai_rag plugin)
# ============================================================================

@router.post("/course/materials/upload")
async def upload_course_material(
    file: UploadFile = File(...),
    course_id: str = Form(...),
    course_name: str = Form("")
):
    """
    Upload a single course material file.
    
    This endpoint is used by the Moodle local_assign_ai_rag plugin
    to upload course materials (PDF, PPTX, DOCX, etc.) for ingestion
    into the RAG knowledge base.
    
    Args:
        file: The file to upload
        course_id: Moodle course ID
        course_name: Moodle course name (optional)
    
    Returns:
        Success status with chunk count
    """
    logger.info(f"Course material upload for course {course_id}: {file.filename}")
    
    try:
        grader = get_grader()
        
        # Validate file type
        valid_extensions = ['.pdf', '.pptx', '.ppt', '.docx', '.doc', '.txt']
        ext = Path(file.filename).suffix.lower()
        if ext not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {file.filename}. Allowed: {', '.join(valid_extensions)}"
            )
        
        # Save uploaded file
        from ..utils import DATA_DIR
        upload_dir = DATA_DIR / "uploads" / f"course_{course_id}"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = upload_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved file: {file_path}")
        
        # Ingest document
        result = grader.ingest_course_materials([file_path], course_id=str(course_id))
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['message'])
        
        return {
            "success": True,
            "message": f"Successfully uploaded and processed {file.filename}",
            "filename": file.filename,
            "course_id": course_id,
            "chunk_count": result.get('chunks_created', 0),
            "documents_loaded": result.get('documents_loaded', 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading course material: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/course/materials/clear")
async def clear_course_materials(course_id: str = Form(None)):
    """
    Clear all materials for a specific course from the knowledge base.
    
    Note: Currently clears the entire vector store.
    Future enhancement: per-course collections.
    
    Args:
        course_id: Moodle course ID
    
    Returns:
        Success status
    """
    logger.info(f"Clearing course materials for course {course_id}")
    
    try:
        grader = get_grader()
        grader.clear_vector_store(str(course_id))
        
        # Also clear uploaded files for this course
        if course_id:
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
        
    except Exception as e:
        logger.error(f"Error clearing course materials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/course/materials/file")
async def delete_course_material_file(
    course_id: str = Form(...),
    filename: str = Form(...)
):
    """
    Delete a single course material file and its vector chunks.
    """
    logger.info(f"Moodle delete request for file '{filename}' in course {course_id}")
    try:
        grader = get_grader()
        success = grader.delete_course_material_file(course_id, filename)
        
        # Also clean up the saved file on disk if it exists
        from ..utils import DATA_DIR
        file_path = DATA_DIR / "uploads" / f"course_{course_id}" / filename
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Removed file from disk: {file_path}")
            
        return {
            "success": success,
            "message": f"Successfully deleted vectors for '{filename}'" if success else f"No vectors found or failed to delete for '{filename}'",
            "course_id": course_id,
            "filename": filename
        }
    except Exception as e:
        logger.error(f"Error deleting course material file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/course/materials/status/{course_id}")
async def get_course_materials_status(course_id: str):
    """
    Get the status of course materials in the knowledge base.
    
    Args:
        course_id: Moodle course ID
    
    Returns:
        Material statistics
    """
    try:
        grader = get_grader()
        vs_info = grader.rag_pipeline.get_vectorstore_info(str(course_id))
        
        # Check uploaded files
        from ..utils import DATA_DIR
        upload_dir = DATA_DIR / "uploads" / f"course_{course_id}"
        uploaded_files = []
        if upload_dir.exists():
            uploaded_files = [f.name for f in upload_dir.iterdir() if f.is_file()]
        
        return {
            "success": True,
            "course_id": course_id,
            "document_count": vs_info.get('document_count', 0),
            "collection_name": vs_info.get('collection_name', 'default'),
            "uploaded_files": uploaded_files,
            "files_count": len(uploaded_files)
        }
        
    except Exception as e:
        logger.error(f"Error getting course materials status: {e}")
        return {
            "success": False,
            "course_id": course_id,
            "error": str(e)
        }


@router.get("/assign/status")
async def assign_server_status():
    """
    Simple health check endpoint for the assignment grading service.
    Used by aiprovider_rag to check if the server is available.
    """
    try:
        grader = get_grader()
        vs_info = grader.rag_pipeline.get_vectorstore_info()
        llm_info = grader.rag_pipeline.get_llm_info()
        
        return {
            "status": "ok",
            "ready": True,
            "document_count": vs_info.get('document_count', 0),
            "llm_provider": llm_info.get('provider', 'unknown'),
            "llm_model": llm_info.get('model', 'unknown')
        }
    except Exception as e:
        return {
            "status": "error",
            "ready": False,
            "error": str(e)
        }
