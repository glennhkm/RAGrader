"""FastAPI application for RAG Essay Grading System.

This application provides:
1. Standard RAG endpoints for essay grading
2. Moodle-compatible endpoints for integration with the Moodle plugins
3. Generic, LMS-agnostic ``/v1`` namespace endpoints

Importing this module has no side effects: the grader, vector store, LLM
clients and Redis locks are created by the application lifespan (see
``create_app``), so tooling and tests can import it safely. ``app`` remains
the ASGI entrypoint used by gunicorn/uvicorn (``src.api.app:app``).
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional
import re
import time
import uuid

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from .models import (
    ChunkingConfig,
    UploadResponse,
    GradeRequest,
    GradeResponse,
    SystemStatus,
    HealthResponse
)
from ..utils import setup_logging, ensure_directories, get_settings, DATA_DIR
from ..utils.config import Settings
from .moodle_routes import router as moodle_router
from .v1_routes import router as v1_router
from .auth import check_api_auth
from .request_utils import API_VERSION, safe_filename, save_upload
from .locking import LockAcquisitionError
from ..vectorstore.embeddings import EmbeddingMismatchError
from .runtime import AppRuntime, build_runtime, get_runtime, is_runtime_ready, set_runtime


API_DESCRIPTION = """
AI-powered essay grading with RAG (Retrieval-Augmented Generation) and course materials.

## Features
- **Course Material Ingestion**: Upload PDF, PPTX, DOCX and TXT files to build a course knowledge base
- **RAG-based Grading**: Grade essays using relevant course materials as context
- **Rubric Support**: Support for structured rubric-based grading
- **Moodle Integration**: Compatible with the Moodle plugins (`/assign/answer`, `/course/materials/*`)
- **Generic API**: Namespace-isolated `/v1/namespaces/{namespace}/*` endpoints for any LMS
"""

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

legacy_router = APIRouter(tags=["System & Legacy"])


def get_grader():
    """Return the grader of the running application."""
    return get_runtime().grader


def get_operation_locks():
    """Return the shared lock manager of the running application."""
    return get_runtime().operation_locks


@legacy_router.get("/", response_model=HealthResponse)
def root():
    """Root endpoint (liveness; does not touch shared state)."""
    return HealthResponse(status="healthy", version=API_VERSION)


@legacy_router.get("/health", response_model=HealthResponse)
def health_check():
    """Readiness check for the API and its shared state services."""
    if not is_runtime_ready():
        raise HTTPException(status_code=503, detail="API runtime not initialized")
    try:
        get_grader().rag_pipeline.vectorstore.heartbeat()
        get_operation_locks().ping()
        return HealthResponse(status="healthy", version=API_VERSION)
    except Exception as exc:
        logger.error(f"Dependency health check failed: {exc}")
        raise HTTPException(status_code=503, detail="Shared state service unavailable")


@legacy_router.get("/status", response_model=SystemStatus)
def get_status():
    """Get system status."""
    try:
        with get_operation_locks().read("course:default"):
            status = get_grader().get_system_status()
        return SystemStatus(**status)
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.post("/upload", response_model=UploadResponse)
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

        grader = get_grader()
        # Save and ingest atomically with respect to other default-collection
        # operations across every API replica.
        with get_operation_locks().write("course:default"):
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
    except (HTTPException, EmbeddingMismatchError):
        raise
    except Exception as e:
        logger.error(f"Error uploading materials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.post("/grade", response_model=GradeResponse)
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
        with get_operation_locks().read("course:default"):
            result = get_grader().grade_essay(
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
    except (HTTPException, EmbeddingMismatchError):
        raise
    except Exception as e:
        logger.error(f"Error grading essay: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.post("/clear")
def clear_database():
    """Clear all documents from vector database."""
    try:
        with get_operation_locks().write("course:default"):
            get_grader().clear_vector_store()
        return {"success": True, "message": "Vector database cleared successfully"}
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.post("/config/chunking")
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
        operation_locks = get_operation_locks()
        if operation_locks.enabled:
            raise HTTPException(
                status_code=409,
                detail="Runtime chunking changes are disabled with API replicas; update the deployment environment",
            )
        with operation_locks.write("course:default"):
            get_grader().update_chunking_config(
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap
            )
        return {
            "success": True,
            "message": "Chunking configuration updated",
            "config": config.model_dump()
        }
    except LockAcquisitionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (HTTPException, EmbeddingMismatchError):
        raise
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


async def embedding_mismatch_handler(_request: Request, exc: EmbeddingMismatchError) -> JSONResponse:
    """A collection built with another embedding setup is a configuration conflict."""
    logger.error(f"Embedding configuration mismatch: {exc}")
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def create_app(runtime: Optional[AppRuntime] = None, settings: Optional[Settings] = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        runtime: Pre-built runtime (tests/embedding). When given, the lifespan
            only registers it and skips logging/directory setup and service
            construction; the caller owns those resources.
        settings: Settings used to build the runtime when none is injected
            (defaults to ``get_settings()``).

    The runtime is built during startup, so failures such as an unreachable
    Chroma server or Redis abort startup instead of serving broken requests.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if runtime is not None:
            active = runtime
        else:
            setup_logging()
            ensure_directories()
            active = build_runtime(settings)
        set_runtime(active)
        logger.info("FastAPI application started")
        try:
            yield
        finally:
            set_runtime(None)
            logger.info("FastAPI application stopped")

    application = FastAPI(
        title="RAG Essay Grading API",
        description=API_DESCRIPTION,
        version=API_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    application.middleware("http")(log_http_request)
    application.add_exception_handler(EmbeddingMismatchError, embedding_mismatch_handler)
    application.include_router(legacy_router)
    application.include_router(moodle_router)
    application.include_router(v1_router)
    return application


app = create_app()


def __getattr__(name: str) -> Any:
    """Backward-compatible access to ``src.api.app.grader`` / ``operation_locks``."""
    if name == "grader":
        return get_grader()
    if name == "operation_locks":
        return get_operation_locks()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    import uvicorn

    api_settings = get_settings().api
    logger.info(f"Starting FastAPI server on {api_settings.host}:{api_settings.port}")
    uvicorn.run(
        "src.api.app:app",
        host=api_settings.host,
        port=api_settings.port,
        reload=True
    )
