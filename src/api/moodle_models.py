"""Pydantic models for Moodle API compatibility."""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional


class MoodleAssignRequest(BaseModel):
    """
    Request model for Moodle assignment grading.
    
    This matches the payload format sent by local_assign_ai_rag plugin.
    """
    # Course context
    course_id: int = Field(..., gt=0, description="Moodle course ID")
    course_name: str = Field(default="", description="Course full name")
    
    # Assignment context
    assignment_id: int = Field(default=0, description="Assignment ID in Moodle")
    assignment_title: str = Field(default="", description="Assignment title/name")
    question: str = Field(..., min_length=1, description="The assignment question/prompt")
    
    # Student submission
    essay: str = Field(..., min_length=1, description="Student's answer/essay text")
    student_name: str = Field(default="", description="Student's full name")
    userid: int = Field(default=0, description="Moodle user ID")
    
    # Grading parameters
    rubric: Dict[str, Any] = Field(default_factory=dict, description="Grading rubric structure")
    maximum_grade: float = Field(default=100.0, gt=0, le=10000, description="Maximum possible grade")
    
    # Additional metadata
    cmi_id: int = Field(default=0, description="Course module ID")
    lang: str = Field(default="en", description="Language code")
    moodle_site_id: str = Field(default="", description="Moodle site identifier")


class MoodleCriterionScore(BaseModel):
    """Score for individual rubric criterion."""
    score: float = Field(..., description="Score for this criterion")
    feedback: str = Field(default="", description="Feedback for this criterion")
    evidence: Optional[str] = Field(default=None, description="Evidence from course materials")


class MoodleCitation(BaseModel):
    """Citation from course materials."""
    text: str = Field(..., description="Quoted text from source")
    source: str = Field(default="Unknown", description="Source document name")
    page: Optional[int] = Field(default=None, description="Page number if available")


class MoodleRetrievedDoc(BaseModel):
    """Retrieved document information."""
    content: str = Field(..., description="Content snippet")
    source: str = Field(default="Unknown", description="Source document")
    page: Any = Field(default=None, description="Page number")


class MoodleAssignResponse(BaseModel):
    """
    Response model for Moodle assignment grading.
    
    This format is expected by local_assign_ai_rag plugin.
    """
    success: bool = Field(default=True, description="Whether grading was successful")
    score: float = Field(default=0.0, description="Numeric score")
    feedback: str = Field(default="", description="Overall feedback text")
    criterion_scores: Dict[str, MoodleCriterionScore] = Field(
        default_factory=dict,
        description="Per-criterion scores if rubric was provided"
    )
    citations: List[MoodleCitation] = Field(
        default_factory=list,
        description="Citations from course materials"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    retrieved_documents: List[MoodleRetrievedDoc] = Field(
        default_factory=list,
        description="Documents retrieved from vector store"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    
    # Legacy fields for backward compatibility with datacurso format
    reply: str = Field(default="", description="Alias for feedback")
    grade: Optional[float] = Field(default=None, description="Alias for score")
    rubric_response: Dict[str, Any] = Field(
        default_factory=dict,
        description="Alias for criterion_scores"
    )


class MoodleUploadRequest(BaseModel):
    """Request model for uploading course materials."""
    course_id: int = Field(..., description="Moodle course ID")
    chunk_size: int = Field(default=500, ge=100, le=2000, description="Text chunk size")
    chunk_overlap: int = Field(default=50, ge=0, le=500, description="Overlap between chunks")
    moodle_site_id: str = Field(default="", description="Moodle site identifier")


class MoodleUploadResponse(BaseModel):
    """Response model for material upload."""
    success: bool
    message: str
    course_id: int
    documents_loaded: int = 0
    chunks_created: int = 0
    total_documents_in_db: int = 0
    errors: List[str] = Field(default_factory=list)


class MoodleCollectionResponse(BaseModel):
    """Response model for collection info."""
    success: bool
    course_id: int
    collection_name: str
    document_count: int = 0
    embedding_model: str = ""


class MoodleStatusResponse(BaseModel):
    """Response model for server status."""
    status: str
    version: str = "1.1.1"
    vectorstore: Dict[str, Any] = Field(default_factory=dict)
    llm_info: Dict[str, Any] = Field(default_factory=dict)
    embedding_model: str = ""
    ready: bool = True
