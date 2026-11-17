"""Helpers for ChromaDB collection naming and metadata-scoped filtering."""

import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence


_NON_ALNUM_RE = re.compile(r"[^a-z0-9_-]+")
_COLLAPSE_UNDERSCORE_RE = re.compile(r"_+")


def _slugify(value: str) -> str:
    lowered = value.strip().lower().replace("/", "_").replace("-", "_").replace(" ", "_")
    cleaned = _NON_ALNUM_RE.sub("_", lowered)
    return _COLLAPSE_UNDERSCORE_RE.sub("_", cleaned).strip("_-")


def build_collection_name(
    base_collection_name: str,
    embedding_model: str,
    namespace: Optional[str] = None,
) -> str:
    """Build a Chroma-safe (3-63 char) collection name for a namespace + model.

    Preserves the exact ``course_{id}_{sanitized_model}`` naming used by existing
    integer Moodle course IDs while safely bounding arbitrary namespace strings.
    """
    sanitized_model = _slugify(embedding_model) or "default_model"
    if namespace is None or not str(namespace).strip():
        prefix = _slugify(base_collection_name) or "materials"
        candidate = f"{prefix}_{sanitized_model}"
    else:
        raw_ns = str(namespace).strip()
        sanitized_ns = _slugify(raw_ns) or "ns"
        if raw_ns.isdigit():
            candidate = f"course_{sanitized_ns}_{sanitized_model}"
        else:
            candidate = f"ns_{sanitized_ns}_{sanitized_model}"

    if len(candidate) <= 63:
        return candidate

    digest = hashlib.sha1(f"{namespace or ''}:{embedding_model}".encode("utf-8")).hexdigest()[:8]
    model_tail = sanitized_model[:18].strip("_-") or "model"
    ns_head = candidate[: 63 - len(model_tail) - len(digest) - 2].strip("_-") or "ns"
    return f"{ns_head}_{digest}_{model_tail}"[:63].strip("_-")


def sanitize_chunk_metadata(
    module: Optional[str] = None,
    tags: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize optional module/tag metadata into Chroma scalar primitives."""
    metadata: Dict[str, Any] = {}
    if module is not None and str(module).strip():
        metadata["module"] = str(module).strip()

    if tags:
        for key, value in tags.items():
            if value is None:
                continue
            clean_key = _slugify(str(key))
            if not clean_key:
                continue
            prefixed = clean_key if clean_key.startswith("tag_") else f"tag_{clean_key}"
            if isinstance(value, (bool, int, float, str)):
                metadata[prefixed] = value
            else:
                metadata[prefixed] = str(value)
    return metadata


def _build_field_clause(field: str, values: Sequence[str]) -> Optional[Dict[str, Any]]:
    cleaned = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return {field: {"$eq": cleaned[0]}}
    return {field: {"$in": cleaned}}


def build_chroma_where_filter(
    modules: Optional[Sequence[str]] = None,
    sources: Optional[Sequence[str]] = None,
    tags: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Construct a Chroma ``where`` filter dict from optional scope criteria."""
    clauses: List[Dict[str, Any]] = []

    if modules:
        clause = _build_field_clause("module", modules)
        if clause:
            clauses.append(clause)

    if sources:
        clause = _build_field_clause("source", sources)
        if clause:
            clauses.append(clause)

    if tags:
        for key, value in tags.items():
            if value is None:
                continue
            clean_key = _slugify(str(key))
            if not clean_key:
                continue
            field = clean_key if clean_key.startswith("tag_") else f"tag_{clean_key}"
            if isinstance(value, (list, tuple, set)):
                clause = _build_field_clause(field, list(value))
                if clause:
                    clauses.append(clause)
            else:
                clauses.append({field: {"$eq": value if isinstance(value, (bool, int, float)) else str(value)}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
