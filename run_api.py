#!/usr/bin/env python3
"""
Main entry point for FastAPI server.
Run this to start the REST API.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import uvicorn
from src.utils import load_config, setup_logging

if __name__ == "__main__":
    # Setup
    setup_logging()
    config = load_config()
    
    # Get API config
    host = config.get('api', {}).get('host', '0.0.0.0')
    port = config.get('api', {}).get('port', 8000)
    
    # Run server
    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=True
    )
