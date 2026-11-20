"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

from .. import __version__


class ChunkingConfig(BaseModel):
    """Chunking configuration."""
    chunk_size: int = Field(default=500, ge=100, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)


class UploadResponse(BaseModel):
    """Response for document upload."""
    success: bool
    message: str
    documents_loaded: int
    chunks_created: int
    total_documents_in_db: int = 0


class GradeRequest(BaseModel):
    """Request for essay grading."""
    question: str = Field(..., min_length=1, description="The question/prompt that was asked")
    essay: str = Field(..., min_length=1, description="Student's answer/essay")
    rubric: Dict[str, Any] = Field(..., description="Grading rubric")


class CriterionScore(BaseModel):
    """Score for individual criterion."""
    score: float
    feedback: str
    evidence: Optional[str] = None


class Citation(BaseModel):
    """Citation from course materials."""
    text: str
    source: str
    page: Optional[int] = None


class RetrievedDocument(BaseModel):
    """Retrieved document information."""
    content: str
    source: str
    page: Any


class GradeResponse(BaseModel):
    """Response for essay grading."""
    success: bool
    score: float = 0
    feedback: str = ""
    criterion_scores: Dict[str, CriterionScore] = {}
    citations: List[Citation] = []
    confidence: float = 0.0
    retrieved_documents: List[RetrievedDocument] = []
    error: Optional[str] = None


class SystemStatus(BaseModel):
    """System status information."""
    vectorstore: Dict[str, Any]
    chunking_config: Dict[str, Any]
    llm_model: str
    embedding_model: str
    # Includes reranker_fallback / reranker_error when the configured reranker failed to start.
    retriever_config: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str = __version__
