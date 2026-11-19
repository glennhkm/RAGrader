"""Prompt builder for rubric-aware grading in English or Indonesian."""

from typing import List, Dict, Any, Optional
import json
from langchain_core.documents import Document
from loguru import logger

from ..utils.config import get_settings
from .prompts import CONTEXT_LABELS, PROMPT_TEMPLATES, resolve_language


class PromptBuilder:
    """Build prompts for rubric-aware essay grading."""
    
    def __init__(self, language: Optional[str] = None):
        """
        Initialize prompt builder.

        Args:
            language: Default prompt language: "auto" (detect from question and
                answer), "en" or "id". Defaults to PROMPT_LANGUAGE.
        """
        self.default_language = language or get_settings().prompt.language
        # Legacy attribute: the historical (Indonesian) template.
        self.template = self._get_template()
        self.last_prompt: Optional[str] = None
        self.last_language: Optional[str] = None
    
    def _get_template(self, language: str = "id") -> str:
        """Get the grading prompt template for a language."""
        return PROMPT_TEMPLATES[language]

    def resolve_language(self, question: str, essay: str, language: Optional[str] = None) -> str:
        """Language for this request: explicit override -> builder default -> detection."""
        return resolve_language(language, self.default_language, question, essay)
    
    def build_prompt(
        self,
        question: str,
        essay: str,
        rubric: Dict[str, Any],
        retrieved_docs: List[Document],
        language: Optional[str] = None,
    ) -> str:
        """
        Build grading prompt with question context.
        
        Args:
            question: The question/prompt that was asked
            essay: Student essay/answer text
            rubric: Grading rubric dictionary
            retrieved_docs: Retrieved course material documents
            language: Optional per-request language ("auto", "en", "id")
            
        Returns:
            Formatted prompt string
        """
        lang = self.resolve_language(question, essay, language)
        rubric_text = self._format_rubric(rubric)
        context_text = self._format_context(retrieved_docs, lang)
        
        prompt = PROMPT_TEMPLATES[lang].format(
            question=question,
            rubric=rubric_text,
            context=context_text,
            essay=essay
        )
        
        # Store the last built prompt for debugging/evaluation
        self.last_prompt = prompt
        self.last_language = lang
        
        logger.info(f"Built {lang} prompt with question and {len(retrieved_docs)} context documents")
        return prompt
    
    def _format_rubric(self, rubric: Dict[str, Any]) -> str:
        """
        Format rubric for prompt.
        
        Args:
            rubric: Rubric dictionary
            
        Returns:
            Formatted rubric string
        """
        try:
            # Handle different rubric formats
            if isinstance(rubric, dict):
                formatted = json.dumps(rubric, indent=2)
            else:
                formatted = str(rubric)
            
            return formatted
            
        except Exception as e:
            logger.warning(f"Error formatting rubric: {e}")
            return str(rubric)
    
    def _format_context(self, documents: List[Document], language: str = "id") -> str:
        """
        Format retrieved documents as context.
        
        Args:
            documents: List of retrieved documents
            language: Prompt language for the labels
            
        Returns:
            Formatted context string
        """
        labels = CONTEXT_LABELS.get(language, CONTEXT_LABELS["id"])
        if not documents:
            return labels["no_material"]
        
        context_parts = []
        for i, doc in enumerate(documents, 1):
            source = doc.metadata.get('source', labels["unknown_source"])
            page = doc.metadata.get('page', 'N/A')
            header = labels["document"].format(index=i, source=source, page=page)
            context_parts.append(f"{header}\n{doc.page_content}\n")
        
        return "\n".join(context_parts)
    
    def parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response into structured format.
        
        Args:
            response: LLM response text
            
        Returns:
            Parsed response dictionary
        """
        try:
            # Try to extract JSON from response
            # Find JSON block
            start = response.find('{')
            end = response.rfind('}') + 1
            
            if start != -1 and end > start:
                json_str = response[start:end]
                parsed = json.loads(json_str)
                return parsed
            else:
                logger.warning("No JSON object found in the LLM response")
                return self._create_fallback_response(response)
                
        except json.JSONDecodeError as e:
            logger.warning(f"Error parsing LLM JSON response: {e}")
            return self._create_fallback_response(response)
    
    def _create_fallback_response(self, raw_response: str) -> Dict[str, Any]:
        """
        Create fallback response when parsing fails.
        
        Args:
            raw_response: Raw LLM response
            
        Returns:
            Fallback response dictionary
        """
        return {
            "score": 0,
            "feedback": raw_response,
            "criterion_scores": {},
            "citations": [],
            "confidence": 0.5,
            "error": "Failed to parse structured LLM response"
        }
