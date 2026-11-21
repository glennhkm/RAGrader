"""Pydantic models for generic /v1/ namespace-scoped autograding endpoints."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class V1MaterialFilter(BaseModel):
    """Optional retrieval scope filter (e.g., Weeks 1-3 modules or specific filenames)."""

    modules: List[str] = Field(default_factory=list, description="Restrict retrieval to these module/week tags")
    sources: List[str] = Field(default_factory=list, description="Restrict retrieval to these filenames")
    tags: Dict[str, Any] = Field(default_factory=dict, description="Additional scalar tag filters")


class V1GradeRequest(BaseModel):
    """Generic autograding request supporting optional rubric and material scope filtering."""

    question: str = Field(..., min_length=1, description="Quiz/assignment question prompt")
    essay: str = Field(..., min_length=1, description="Student answer text")
    rubric: Dict[str, Any] = Field(default_factory=dict, description="Optional rubric criteria dictionary")
    maximum_grade: float = Field(default=100.0, gt=0, le=10000, description="Maximum grade scale")
    material_filter: Optional[V1MaterialFilter] = Field(
        default=None,
        description="Optional scope filter limiting retrieval to selected modules, filenames, or tags",
    )
    language: Optional[Literal["auto", "en", "id"]] = Field(
        default=None,
        description="Prompt/feedback language; defaults to PROMPT_LANGUAGE (auto detects from the question and answer)",
    )


class V1CriterionScore(BaseModel):
    """Score and feedback for a single rubric criterion."""

    score: float
    feedback: str = ""
    evidence: Optional[str] = None


class V1Citation(BaseModel):
    """Citation snippet referencing an indexed source document."""

    text: str
    source: str = "Unknown"
    page: Optional[int] = None


class V1RetrievedDoc(BaseModel):
    """Retrieved material chunk passed to the grader."""

    content: str
    source: str = "Unknown"
    page: Any = None


class V1GradeResponse(BaseModel):
    """Structured grading output for a namespace-scoped request."""

    success: bool = True
    namespace: str
    score: float = 0.0
    feedback: str = ""
    criterion_scores: Dict[str, V1CriterionScore] = Field(default_factory=dict)
    citations: List[V1Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    retrieved_documents: List[V1RetrievedDoc] = Field(default_factory=list)
    language: Optional[str] = Field(default=None, description="Prompt language used for grading")
    integrity_warnings: List[str] = Field(
        default_factory=list,
        description="Reasons the grade needs human review (e.g. possible prompt injection, "
        "ungrounded citations removed); when present, confidence is capped at 0.3",
    )
    error: Optional[str] = None


class V1UploadResponse(BaseModel):
    """Response model for namespace material ingestion."""

    success: bool
    message: str
    namespace: str
    filename: str
    module: Optional[str] = None
    topic: Optional[str] = None
    tags: Dict[str, Any] = Field(default_factory=dict)
    chunk_count: int = 0
    documents_loaded: int = 0


class V1NamespaceInfoResponse(BaseModel):
    """Response model summarizing indexed materials within a namespace."""

    success: bool
    namespace: str
    collection_name: str
    document_count: int = 0
    uploaded_files: List[str] = Field(default_factory=list)
    embedding_model: str = ""


class V1DeleteResponse(BaseModel):
    """Response model for namespace or file deletion."""

    success: bool
    message: str
    namespace: str
    filename: Optional[str] = None
