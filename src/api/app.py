"""FastAPI application for RAG Essay Grading System.

This application provides:
1. Standard RAG endpoints for essay grading
2. Moodle-compatible endpoints for integration with local_assign_ai_rag plugin

The Moodle integration endpoints are prefixed and follow the format
expected by the Moodle plugin for seamless LMS integration.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pathlib import Path
import shutil
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
from ..utils import load_config, setup_logging, ensure_directories, DATA_DIR


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
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware - allow all origins for Moodle integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load config and initialize grader
config = load_config()
grader = EssayGrader(
    config,
    provider=config.get('llm', {}).get('provider', 'provider_chain'),
    model_name=config.get('llm', {}).get('model_name')
)

# Import and include Moodle routes
from .moodle_routes import router as moodle_router
app.include_router(moodle_router)

logger.info("FastAPI application initialized with Moodle integration")


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.get("/status", response_model=SystemStatus)
async def get_status():
    """Get system status."""
    try:
        status = grader.get_system_status()
        return SystemStatus(**status)
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload", response_model=UploadResponse)
async def upload_materials(
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
            if not file.filename.endswith('.pdf'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type: {file.filename}. Only PDF files are allowed."
                )
        
        # Update chunking config
        grader.update_chunking_config(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # Save uploaded files
        upload_dir = DATA_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_paths = []
        for file in files:
            file_path = upload_dir / file.filename
            
            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            pdf_paths.append(file_path)
            logger.info(f"Saved file: {file.filename}")
        
        # Ingest documents
        result = grader.ingest_course_materials(pdf_paths)
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=result['message'])
        
        return UploadResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading materials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/grade", response_model=GradeResponse)
async def grade_essay(request: GradeRequest):
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error grading essay: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clear")
async def clear_database():
    """Clear all documents from vector database."""
    try:
        grader.clear_vector_store()
        return {"success": True, "message": "Vector database cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/config/chunking")
async def update_chunking_config(config: ChunkingConfig):
    """
    Update chunking configuration.
    
    Args:
        config: New chunking configuration
        
    Returns:
        Success message
    """
    try:
        grader.update_chunking_config(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
        return {
            "success": True,
            "message": "Chunking configuration updated",
            "config": config.dict()
        }
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
