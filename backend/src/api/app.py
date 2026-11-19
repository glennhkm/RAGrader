"""FastAPI application for RAG Essay Grading System.

This application provides:
1. Standard RAG endpoints for essay grading
2. Moodle-compatible endpoints for integration with local_assign_ai_rag plugin

The Moodle integration endpoints are prefixed and follow the format
expected by the Moodle plugin for seamless LMS integration.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from typing import List
from pathlib import Path
import re
import time
import uuid
from loguru import logger

from .models import (
    ChunkingConfig,
    UploadResponse,
    GradeRequest,
    GradeResponse,
    SystemStatus,
    HealthResponse
)
from ..grading import EssayGrader
from ..utils import load_config, setup_logging, ensure_directories, get_settings, DATA_DIR
from .moodle_routes import router as moodle_router
from .v1_routes import router as v1_router
from .auth import check_api_auth
from .request_utils import API_VERSION, safe_filename, save_upload
from .locking import LockAcquisitionError, OperationLockManager


# Initialize
setup_logging()
ensure_directories()

# Create FastAPI app
app = FastAPI(
    title="RAG Essay Grading API",
    description="""
AI-powered essay grading with RAG (Retrieval-Augmented Generation) and course materials.

## Features
- **Course Material Ingestion**: Upload PDFs and PPTXs to build course knowledge base
- **RAG-based Grading**: Grade essays using relevant course materials as context
- **Rubric Support**: Support for structured rubric-based grading
- **Moodle Integration**: Compatible with Moodle LMS via local_assign_ai_rag plugin

## Moodle Integration
Use the `/assign/answer` endpoint for Moodle assignment grading.
    """,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Load config and initialize grader
config = load_config()
grader = EssayGrader(
    config,
    provider=config.get('llm', {}).get('provider', 'provider_chain'),
    model_name=config.get('llm', {}).get('model_name')
)
operation_locks = OperationLockManager()

app.include_router(moodle_router)
app.include_router(v1_router)

logger.info("FastAPI application initialized with Moodle integration")


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@app.middleware("http")
async def log_http_request(request: Request, call_next):
    """Log request outcome and expose a correlation ID without logging payloads."""
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else uuid.uuid4().hex
    started = time.monotonic()
    status_code = 500

    with logger.contextualize(request_id=request_id):
        logger.info(f"HTTP request started method={request.method} path={request.url.path}")
        try:
            denied = check_api_auth(request)
            response = denied if denied is not None else await call_next(request)
            status_code = response.status_code
        except Exception:
            logger.exception("Unhandled HTTP request error")
            raise
        finally:
            duration_ms = (time.monotonic() - started) * 1000
            logger.info(
                f"HTTP request finished method={request.method} path={request.url.path} "
                f"status={status_code} duration_ms={duration_ms:.1f}"
            )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-API-Instance"] = get_settings().api.instance_id
    return response


@app.get("/", response_model=HealthResponse)
def root():
    """Root endpoint."""
    return HealthResponse(status="healthy", version=API_VERSION)


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Readiness check for the API and its shared state services."""
    try:
        grader.rag_pipeline.vectorstore.heartbeat()
        operation_locks.ping()
        return HealthResponse(status="healthy", version=API_VERSION)
    except Exception as exc:
        logger.error(f"Dependency health check failed: {exc}")
        raise HTTPException(status_code=503, detail="Shared state service unavailable")


@app.get("/status", response_model=SystemStatus)
def get_status():
    """Get system status."""
    try:
        with operation_locks.read("course:default"):
            status = grader.get_system_status()
        return SystemStatus(**status)
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload", response_model=UploadResponse)
def upload_materials(
    files: List[UploadFile] = File(...),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50)
):
    """
    Upload and ingest course material PDFs.
    
    Args:
        files: List of PDF files
        chunk_size: Size of text chunks
        chunk_overlap: Overlap between chunks
        
    Returns:
        Upload status and statistics
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        # Validate files are PDFs
        for file in files:
            filename = safe_filename(file.filename)
            if Path(filename).suffix.lower() != '.pdf':
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type: {file.filename}. Only PDF files are allowed."
                )
        
        # Update chunking config
        if not 100 <= chunk_size <= 2000:
            raise HTTPException(status_code=400, detail="chunk_size must be between 100 and 2000")
        if not 0 <= chunk_overlap < chunk_size:
            raise HTTPException(status_code=400, detail="chunk_overlap must be smaller than chunk_size")
        
        # Save and ingest atomically with respect to other default-collection
        # operations across every API replica.
        with operation_locks.write("course:default"):
            upload_dir = DATA_DIR / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)

            pdf_paths = []
            for file in files:
                filename = safe_filename(file.filename)
                file_path = upload_dir / filename
                save_upload(file, file_path)

                pdf_paths.append(file_path)
                logger.info(f"Saved file: {filename}")

            grader.update_chunking_config(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            result = grader.ingest_course_materials(pdf_paths)
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['message'])
        
        return UploadResponse(**result)
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading materials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/grade", response_model=GradeResponse)
def grade_essay(request: GradeRequest):
    """
    Grade a student essay with question context.
    
    Args:
        request: Grading request with question, essay, and rubric
        
    Returns:
        Grading results with score, feedback, and citations
    """
    try:
        # Validate inputs
        if not request.question or not request.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        
        if not request.essay or not request.essay.strip():
            raise HTTPException(status_code=400, detail="Essay/Answer cannot be empty")
        
        if not request.rubric:
            raise HTTPException(status_code=400, detail="Rubric cannot be empty")
        
        # Grade essay with question context
        with operation_locks.read("course:default"):
            result = grader.grade_essay(
                question=request.question,
                essay=request.essay,
                rubric=request.rubric
            )
        
        if not result.get('success', False):
            error_msg = result.get('error', 'Unknown error occurred')
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Convert to response model
        return GradeResponse(**result)
        
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error grading essay: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear")
def clear_database():
    """Clear all documents from vector database."""
    try:
        with operation_locks.write("course:default"):
            grader.clear_vector_store()
        return {"success": True, "message": "Vector database cleared successfully"}
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/config/chunking")
def update_chunking_config(config: ChunkingConfig):
    """
    Update chunking configuration.
    
    Args:
        config: New chunking configuration
        
    Returns:
        Success message
    """
    try:
        if config.chunk_overlap >= config.chunk_size:
            raise HTTPException(status_code=400, detail="chunk_overlap must be smaller than chunk_size")
        if operation_locks.enabled:
            raise HTTPException(
                status_code=409,
                detail="Runtime chunking changes are disabled with API replicas; update the deployment environment",
            )
        with operation_locks.write("course:default"):
            grader.update_chunking_config(
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap
            )
        return {
            "success": True,
            "message": "Chunking configuration updated",
            "config": config.dict()
        }
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    host = config.get('api', {}).get('host', '0.0.0.0')
    port = config.get('api', {}).get('port', 8000)
    
    logger.info(f"Starting FastAPI server on {host}:{port}")
    
    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=True
    )
