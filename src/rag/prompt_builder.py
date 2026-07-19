"""Prompt builder for rubric-aware grading."""

from typing import List, Dict, Any
import json
from langchain_core.documents import Document
from loguru import logger


class PromptBuilder:
    """Build prompts for rubric-aware essay grading."""
    
    def __init__(self):
        """Initialize prompt builder."""
        self.template = self._get_template()
    
    def _get_template(self) -> str:
        """Get the grading prompt template."""
        return """Anda adalah seorang penilai esai ahli. Nilai jawaban mahasiswa berikut berdasarkan pertanyaan yang diajukan, rubrik yang diberikan, dan materi kuliah.

PERTANYAAN/SOAL:
{question}

RUBRIK PENILAIAN:
{rubric}

MATERI KULIAH (Bukti/Referensi):
{context}

JAWABAN MAHASISWA:
{essay}

INSTRUKSI:
1. Pertama, periksa apakah jawaban sesuai dengan pertanyaan yang diajukan
2. Evaluasi jawaban berdasarkan setiap kriteria dalam rubrik
3. Gunakan bukti dari materi kuliah untuk memverifikasi keakuratan
4. Berikan umpan balik spesifik untuk setiap kriteria
5. Field "score" WAJIB berupa persentase keseluruhan 0 sampai 100, terlepas dari nilai maksimum tugas
6. Field skor pada setiap criterion_scores WAJIB mengikuti batas poin kriteria pada rubrik
7. Sertakan kutipan dari materi kuliah

Berikan respons Anda dalam format JSON berikut:
{{
    "score": <persentase keseluruhan 0-100>,
    "feedback": "Umpan balik keseluruhan di sini",
    "criterion_scores": {{
        "nama_kriteria": {{
            "score": <skor>,
            "feedback": "Umpan balik spesifik",
            "evidence": "Kutipan dari materi kuliah"
        }}
    }},
    "citations": [
        {{
            "text": "Teks kutipan dari materi",
            "source": "Referensi sumber",
            "page": <nomor halaman jika tersedia>
        }}
    ],
    "confidence": <0.0 sampai 1.0>
}}

Respons:"""
    
    def build_prompt(
        self,
        question: str,
        essay: str,
        rubric: Dict[str, Any],
        retrieved_docs: List[Document]
    ) -> str:
        """
        Build grading prompt with question context.
        
        Args:
            question: The question/prompt that was asked
            essay: Student essay/answer text
            rubric: Grading rubric dictionary
            retrieved_docs: Retrieved course material documents
            
        Returns:
            Formatted prompt string
        """
        # Format rubric
        rubric_text = self._format_rubric(rubric)
        
        # Format context from retrieved documents
        context_text = self._format_context(retrieved_docs)
        
        # Fill template
        prompt = self.template.format(
            question=question,
            rubric=rubric_text,
            context=context_text,
            essay=essay
        )
        
        # Store the last built prompt for debugging/evaluation
        self.last_prompt = prompt
        
        logger.info(f"Built prompt with question and {len(retrieved_docs)} context documents")
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
    
    def _format_context(self, documents: List[Document]) -> str:
        """
        Format retrieved documents as context.
        
        Args:
            documents: List of retrieved documents
            
        Returns:
            Formatted context string
        """
        if not documents:
            return "Tidak ada materi kuliah yang relevan ditemukan."
        
        context_parts = []
        
        for i, doc in enumerate(documents, 1):
            # Extract metadata
            source = doc.metadata.get('source', 'Tidak Diketahui')
            page = doc.metadata.get('page', 'N/A')
            
            # Format document
            context_parts.append(
                f"[Dokumen {i}] (Sumber: {source}, Halaman: {page})\n"
                f"{doc.page_content}\n"
            )
        
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
                logger.warning("Tidak dapat menemukan JSON dalam respons")
                return self._create_fallback_response(response)
                
        except json.JSONDecodeError as e:
            logger.warning(f"Error parsing respons JSON: {e}")
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
            "error": "Gagal mengurai respons terstruktur"
        }
