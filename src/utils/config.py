"""Utility functions for the RAG Essay Grading System."""

import yaml
import os
from pathlib import Path
from typing import Dict, Any
from loguru import logger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = CONFIG_DIR / "config.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    logger.info(f"Configuration loaded from {config_path}")
    return config


def setup_logging(log_level: str = "INFO"):
    """Setup logging configuration."""
    log_file = LOGS_DIR / "app.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.add(
        log_file,
        rotation="500 MB",
        retention="10 days",
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
    )
    logger.info("Logging setup complete")


def ensure_directories():
    """Ensure all required directories exist."""
    directories = [
        DATA_DIR / "uploads",
        DATA_DIR / "chroma_db",
        LOGS_DIR
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    
    logger.info("All required directories verified")


def save_uploaded_file(uploaded_file, filename: str) -> Path:
    """Save uploaded file to data/uploads directory."""
    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / filename
    
    # Handle both file-like objects and binary data
    if hasattr(uploaded_file, 'read'):
        with open(file_path, 'wb') as f:
            f.write(uploaded_file.read())
    else:
        with open(file_path, 'wb') as f:
            f.write(uploaded_file)
    
    logger.info(f"File saved: {file_path}")
    return file_path
