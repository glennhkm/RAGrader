"""Helpers for ChromaDB collection naming and metadata-scoped filtering."""

import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union


_NON_ALNUM_RE = re.compile(r"[^a-z0-9_-]+")
_COLLAPSE_UNDERSCORE_RE = re.compile(r"_+")


def _slugify(value: str) -> str:
    lowered = value.strip().lower().replace("/", "_").replace("-", "_").replace(" ", "_")
    cleaned = _NON_ALNUM_RE.sub("_", lowered)
    return _COLLAPSE_UNDERSCORE_RE.sub("_", cleaned).strip("_-")


def _normalize_tag_key(key: str) -> str:
    clean_key = _slugify(str(key))
    if not clean_key:
        return ""
    return clean_key if clean_key.startswith("tag_") else f"tag_{clean_key}"


def _normalize_scalar(
    value: Any,
    preserve_scalars: bool = True,
) -> Optional[Union[bool, int, float, str]]:
    if value is None:
        return None
    if preserve_scalars and isinstance(value, (bool, int, float)):
        return value
    stripped = str(value).strip()
    return stripped or None


def build_collection_name(
    base_collection_name: str,
    embedding_model: str,
    namespace: Optional[str] = None,
) -> str:
    """Build a Chroma-safe (3-63 char) collection name for a namespace + model.

    Preserves the exact ``course_{id}_{sanitized_model}`` naming used by existing
    ASCII integer Moodle course IDs while deterministically hashing all other
    namespaces so punctuation/casing variants cannot collapse onto one collection.
    """
    sanitized_model = _slugify(embedding_model) or "default_model"
    if namespace is None or not str(namespace).strip():
        prefix = _slugify(base_collection_name) or "materials"
        candidate = f"{prefix}_{sanitized_model}"
        if len(candidate) <= 63:
            return candidate
        digest = hashlib.sha1(f":{embedding_model}".encode("utf-8")).hexdigest()[:8]
        model_tail = sanitized_model[:18].strip("_-") or "model"
        head = candidate[: 63 - len(model_tail) - len(digest) - 2].strip("_-") or "materials"
        return f"{head}_{digest}_{model_tail}"[:63].strip("_-")

    raw_ns = str(namespace).strip()
    sanitized_ns = _slugify(raw_ns) or "ns"
    if raw_ns.isascii() and raw_ns.isdigit():
        candidate = f"course_{sanitized_ns}_{sanitized_model}"
        if len(candidate) <= 63:
            return candidate
        digest = hashlib.sha1(f"{raw_ns}:{embedding_model}".encode("utf-8")).hexdigest()[:8]
        model_tail = sanitized_model[:18].strip("_-") or "model"
        ns_head = candidate[: 63 - len(model_tail) - len(digest) - 2].strip("_-") or "course"
        return f"{ns_head}_{digest}_{model_tail}"[:63].strip("_-")

    digest = hashlib.sha1(raw_ns.encode("utf-8")).hexdigest()[:8]
    candidate = f"ns_{sanitized_ns}_{digest}_{sanitized_model}"
    if len(candidate) <= 63:
        return candidate

    if len(sanitized_model) <= 18:
        model_part = sanitized_model
    else:
        model_hash = hashlib.sha1(embedding_model.encode("utf-8")).hexdigest()[:4]
        model_head = sanitized_model[:13].strip("_-") or "m"
        model_part = f"{model_head}_{model_hash}"

    max_ns_len = 63 - len("ns_") - len(digest) - len(model_part) - 2
    ns_part = sanitized_ns[:max_ns_len].strip("_-") or "ns"
    return f"ns_{ns_part}_{digest}_{model_part}"


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
            prefixed = _normalize_tag_key(str(key))
            if not prefixed:
                continue
            normalized = _normalize_scalar(value, preserve_scalars=True)
            if normalized is not None:
                metadata[prefixed] = normalized
    return metadata


def _build_field_clause(
    field: str,
    values: Sequence[Any],
    preserve_scalars: bool = False,
) -> Optional[Dict[str, Any]]:
    cleaned: List[Union[bool, int, float, str]] = []
    for value in values:
        normalized = _normalize_scalar(value, preserve_scalars=preserve_scalars)
        if normalized is not None:
            cleaned.append(normalized)
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
        clause = _build_field_clause("module", modules, preserve_scalars=False)
        if clause:
            clauses.append(clause)

    if sources:
        clause = _build_field_clause("source", sources, preserve_scalars=False)
        if clause:
            clauses.append(clause)

    if tags:
        for key, value in tags.items():
            if value is None:
                continue
            field = _normalize_tag_key(str(key))
            if not field:
                continue
            if isinstance(value, (list, tuple, set)):
                clause = _build_field_clause(field, list(value), preserve_scalars=True)
                if clause:
                    clauses.append(clause)
            else:
                normalized = _normalize_scalar(value, preserve_scalars=True)
                if normalized is not None:
                    clauses.append({field: {"$eq": normalized}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
