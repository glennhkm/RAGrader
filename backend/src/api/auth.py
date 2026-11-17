"""Optional bearer-token authentication helpers for the FastAPI service."""

import os
import secrets
from typing import Mapping, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

PUBLIC_PATHS = frozenset({"/", "/health"})


def extract_bearer_token(headers: Mapping[str, str]) -> Optional[str]:
    """Extract a bearer token from ``Authorization`` or ``X-API-Key`` headers."""
    normalized = {str(k).lower(): str(v) for k, v in headers.items()}
    auth_header = normalized.get("authorization", "").strip()
    if auth_header:
        scheme, _, value = auth_header.partition(" ")
        if scheme.lower() == "bearer":
            token = value.strip()
            return token or None
        return None

    api_key = normalized.get("x-api-key", "").strip()
    return api_key or None


def check_api_auth(request: Request) -> Optional[JSONResponse]:
    """Enforce ``API_AUTH_TOKEN`` on non-health routes when configured."""
    expected_token = os.getenv("API_AUTH_TOKEN", "").strip()
    if not expected_token or request.url.path in PUBLIC_PATHS:
        return None

    provided_token = extract_bearer_token(request.headers)
    if provided_token and secrets.compare_digest(provided_token, expected_token):
        return None

    return JSONResponse(
        status_code=401,
        content={"detail": "Invalid or missing API token"},
        headers={"WWW-Authenticate": "Bearer"},
    )

