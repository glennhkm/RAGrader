"""Validation and normalization helpers for Moodle-facing API requests."""

from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from fastapi import HTTPException, UploadFile

from .. import __version__
from ..utils.config import get_settings

API_VERSION = __version__
ALLOWED_MATERIAL_EXTENSIONS = frozenset({".pdf", ".pptx", ".docx", ".txt"})
UPLOAD_CHUNK_SIZE = 1024 * 1024


def safe_filename(filename: str) -> str:
    """Return a basename that cannot escape the configured upload directory."""
    normalized = (filename or "").replace("\\", "/")
    basename = Path(normalized).name.strip()
    if not basename or basename in {".", ".."} or len(basename) > 255:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if any(ord(character) < 32 for character in basename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return basename


def validate_material_filename(filename: str) -> str:
    """Validate and normalize a supported course-material filename."""
    basename = safe_filename(filename)
    extension = Path(basename).suffix.lower()
    if extension not in ALLOWED_MATERIAL_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_MATERIAL_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {basename}. Allowed: {allowed}",
        )
    return basename


def save_upload(upload: UploadFile, destination: Path) -> int:
    """Save an upload with a hard size limit and remove partial files on error."""
    max_size_mb = get_settings().api.max_upload_size_mb
    max_size_bytes = max_size_mb * 1024 * 1024
    written = 0
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with destination.open("wb") as target:
            while chunk := upload.file.read(UPLOAD_CHUNK_SIZE):
                written += len(chunk)
                if written > max_size_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {max_size_mb} MB upload limit",
                    )
                target.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return written


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def rubric_maxima(rubric: Mapping[str, Any]) -> Dict[str, float]:
    """Extract criterion maximums from all rubric formats sent by the plugins."""
    if not isinstance(rubric, Mapping) or not rubric:
        return {}

    entries: Any = rubric.get("criteria", rubric)
    if not isinstance(entries, Mapping):
        return {}

    maxima: Dict[str, float] = {}
    for name, definition in entries.items():
        if not isinstance(definition, Mapping):
            continue

        maximum = 0.0
        for key in ("max_score", "max_points", "points"):
            if key in definition:
                maximum = _as_float(definition[key])
                break

        if maximum <= 0 and isinstance(definition.get("levels"), (list, tuple)):
            maximum = max(
                (_as_float(level.get("points", level.get("score")))
                 for level in definition["levels"] if isinstance(level, Mapping)),
                default=0.0,
            )

        if maximum > 0:
            maxima[str(name)] = maximum

    return maxima


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and _as_float(value, float("nan")) == _as_float(value)


def has_usable_score(result: Mapping[str, Any], rubric: Mapping[str, Any]) -> bool:
    """Whether the numbers ``normalize_grade`` would use are really in the response.

    Without this check a missing or non-numeric score silently becomes a grade of 0.
    """
    raw = result.get("criterion_scores", {})
    raw = raw if isinstance(raw, Mapping) else {}
    criteria = {str(k).casefold(): v for k, v in raw.items() if isinstance(v, Mapping)}
    names = [name.casefold() for name in rubric_maxima(rubric)]
    if names and all(name in criteria for name in names):
        return all(_is_number(criteria[name].get("score")) for name in names)
    return _is_number(result.get("score"))


def normalize_grade(
    result: Mapping[str, Any], rubric: Mapping[str, Any], maximum_grade: float
) -> Tuple[float, Dict[str, Dict[str, Any]], float]:
    """Normalize LLM output and scale its percentage to the Moodle grade range."""
    maximum_grade = max(0.0, _as_float(maximum_grade, 100.0))
    raw_criteria = result.get("criterion_scores", {})
    raw_criteria = raw_criteria if isinstance(raw_criteria, Mapping) else {}
    maxima = rubric_maxima(rubric)

    normalized_criteria: Dict[str, Dict[str, Any]] = {}
    for name, data in raw_criteria.items():
        if not isinstance(data, Mapping):
            continue
        maximum = maxima.get(str(name))
        score = max(0.0, _as_float(data.get("score")))
        if maximum is not None:
            score = min(score, maximum)
        normalized_criteria[str(name)] = {
            "score": score,
            "feedback": str(data.get("feedback", "")),
            "evidence": None if data.get("evidence") is None else str(data.get("evidence")),
        }

    # When every rubric criterion is present, criterion points are the most
    # reliable source. Otherwise the prompt-defined overall score is a percent.
    criterion_lookup = {name.casefold(): data for name, data in normalized_criteria.items()}
    if maxima and all(name.casefold() in criterion_lookup for name in maxima):
        total_maximum = sum(maxima.values())
        total_awarded = sum(
            min(criterion_lookup[name.casefold()]["score"], criterion_maximum)
            for name, criterion_maximum in maxima.items()
        )
        percentage = (total_awarded / total_maximum) * 100 if total_maximum else 0.0
    else:
        percentage = _as_float(result.get("score"))

    percentage = min(100.0, max(0.0, percentage))
    scaled_score = min(maximum_grade, (percentage / 100.0) * maximum_grade)

    confidence = _as_float(result.get("confidence"))
    if 1.0 < confidence <= 100.0:
        confidence /= 100.0
    confidence = min(1.0, max(0.0, confidence))
    return round(scaled_score, 2), normalized_criteria, confidence


def optional_page(value: Any) -> int | None:
    """Normalize an optional page field from an LLM response."""
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if page > 0 else None
