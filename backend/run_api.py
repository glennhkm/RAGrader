#!/usr/bin/env python3
"""
Development entry point for the FastAPI server.

Production uses gunicorn with ``src.api.app:app`` (see Dockerfile). Logging,
directories and services are set up by the application lifespan.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import uvicorn
from src.utils import get_settings

if __name__ == "__main__":
    api_settings = get_settings().api

    uvicorn.run(
        "src.api.app:app",
        host=api_settings.host,
        port=api_settings.port,
        reload=True
    )
