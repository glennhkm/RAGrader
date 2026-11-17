"""Utility functions for the RAG Essay Grading System."""

import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, List

import yaml
from loguru import logger
from dotenv import load_dotenv

# Setup project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

# Load environment variables from the project .env first, then fall back to cwd discovery.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def _get_env_value(var_name: str, default: str = None) -> str:
    """Read an environment value, using the placeholder default when provided."""
    value = os.getenv(var_name)
    if value is not None:
        return value
    if default is not None:
        return default
    raise ValueError(
        f"Environment variable {var_name} is required by config.yaml but is not set"
    )


def _coerce_scalar(value: str) -> Any:
    """Convert env strings to common scalar types for config values."""
    stripped = value.strip()
    lowered = stripped.lower()

    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    if lowered in {"none", "null"}:
        return None

    if re.fullmatch(r"[+-]?\d+", stripped):
        try:
            return int(stripped)
        except ValueError:
            return value

    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", stripped):
        try:
            return float(stripped)
        except ValueError:
            return value

    return value


def _resolve_env_placeholders(value: Any) -> Any:
    """Recursively resolve ${VAR:default} placeholders from loaded YAML data."""
    if isinstance(value, dict):
        return {
            key: _resolve_env_placeholders(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_resolve_env_placeholders(item) for item in value]

    if not isinstance(value, str):
        return value

    full_match = ENV_PATTERN.fullmatch(value.strip())
    if full_match:
        env_value = _get_env_value(full_match.group(1), full_match.group(2))
        return _coerce_scalar(env_value)

    def replace_match(match: re.Match) -> str:
        return str(_get_env_value(match.group(1), match.group(2)))

    return ENV_PATTERN.sub(replace_match, value)


def _summarize_env_placeholders(value: Any, names: List[str] = None) -> List[str]:
    """Collect env names referenced by config without exposing values."""
    names = names or []
    if isinstance(value, dict):
        for item in value.values():
            _summarize_env_placeholders(item, names)
    elif isinstance(value, list):
        for item in value:
            _summarize_env_placeholders(item, names)
    elif isinstance(value, str):
        names.extend(match.group(1) for match in ENV_PATTERN.finditer(value))
    return sorted(set(names))


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load YAML configuration and resolve ${VAR:default} placeholders from .env."""
    if config_path is None:
        config_path = CONFIG_DIR / "config.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    env_refs = _summarize_env_placeholders(config)
    config = _resolve_env_placeholders(config)

    logger.info(f"Configuration loaded from {config_path}")
    if env_refs:
        logger.info(f"Configuration env placeholders resolved: {', '.join(env_refs)}")
    return config


def setup_logging(log_level: str = "INFO"):
    """Setup logging configuration."""
    log_file = LOGS_DIR / "app.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    level = os.getenv("LOG_LEVEL", log_level).upper()
    logformat = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
        "request_id={extra[request_id]} | {name}:{function}:{line} - {message}"
    )

    # Replace Loguru's DEBUG default sink and configure both Docker stdout and
    # the persistent file with the same production log level.
    logger.remove()
    logger.configure(extra={"request_id": "-"})
    logger.add(
        sys.stderr,
        level=level,
        format=logformat,
        backtrace=False,
        diagnose=False,
    )
    log_to_file = os.getenv("LOG_TO_FILE", "true").lower() in {"1", "true", "yes", "on"}
    if log_to_file:
        try:
            logger.add(
                log_file,
                rotation="50 MB",
                retention="10 days",
                level=level,
                format=logformat,
                backtrace=False,
                diagnose=False,
                enqueue=True,
            )
        except OSError as exc:
            # Keep the API available through Docker stdout if a local log path
            # is not writable.
            logger.warning(f"Persistent file logging disabled: {exc}")
    logger.info(f"Logging setup complete at level {level}")


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
