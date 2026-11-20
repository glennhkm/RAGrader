"""Utility functions for the RAG Essay Grading System."""

import os
import re
import socket
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

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


def _get_env_value(var_name: str, default: str = None, env: Mapping[str, str] = None) -> str:
    """Read an environment value, using the placeholder default when provided."""
    source = os.environ if env is None else env
    value = source.get(var_name)
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


def _resolve_env_placeholders(value: Any, env: Mapping[str, str] = None) -> Any:
    """Recursively resolve ${VAR:default} placeholders from loaded YAML data."""
    if isinstance(value, dict):
        return {
            key: _resolve_env_placeholders(item, env)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_resolve_env_placeholders(item, env) for item in value]

    if not isinstance(value, str):
        return value

    full_match = ENV_PATTERN.fullmatch(value.strip())
    if full_match:
        env_value = _get_env_value(full_match.group(1), full_match.group(2), env)
        return _coerce_scalar(env_value)

    def replace_match(match: re.Match) -> str:
        return str(_get_env_value(match.group(1), match.group(2), env))

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


def _read_yaml_config(config_path: Path = None, env: Mapping[str, str] = None) -> Dict[str, Any]:
    """Load config.yaml and resolve placeholders against ``env`` (default: os.environ)."""
    config_path = CONFIG_DIR / "config.yaml" if config_path is None else Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
    return _resolve_env_placeholders(config, env)


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load YAML configuration and resolve ${VAR:default} placeholders from .env.

    Kept for backward compatibility; new code should use ``get_settings()``.
    """
    if config_path is None:
        config_path = CONFIG_DIR / "config.yaml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            env_refs = _summarize_env_placeholders(yaml.safe_load(f) or {})
    else:
        env_refs = []
    config = _read_yaml_config(config_path)

    logger.info(f"Configuration loaded from {config_path}")
    if env_refs:
        logger.info(f"Configuration env placeholders resolved: {', '.join(env_refs)}")
    return config


def setup_logging(log_level: str = "INFO"):
    """Setup logging configuration."""
    log_file = LOGS_DIR / "app.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logging_settings = get_settings().logging
    level = logging_settings.level or log_level.upper()
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
    if logging_settings.to_file:
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


# =============================================================================
# Typed settings layer (Cycle 2)
#
# Precedence: process environment -> backend/.env (loaded above, never
# overriding real env vars) -> configs/config.yaml values -> code defaults.
# Components receive these frozen settings by constructor injection and use
# get_settings() only as their default, so tests can build isolated settings
# with load_settings(env={...}) or override_settings(...).
# =============================================================================


class ConfigError(ValueError):
    """Raised when a configuration value is missing or invalid."""


_SECRET_FIELD_MARKERS = ("api_key", "token", "secret", "password")
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_MISSING = object()


def _mask_secret(value: Any) -> str:
    return "'***'" if value else "''"


class _SafeRepr:
    """Dataclass mixin whose repr masks secret-looking fields."""

    def __repr__(self) -> str:  # pragma: no cover - exercised through repr() in tests
        parts = []
        for item in fields(self):
            value = getattr(self, item.name)
            if any(marker in item.name for marker in _SECRET_FIELD_MARKERS):
                rendered = _mask_secret(value)
            elif item.name == "raw":
                rendered = "<resolved config.yaml>"
            else:
                rendered = repr(value)
            parts.append(f"{item.name}={rendered}")
        return f"{type(self).__name__}({', '.join(parts)})"


@dataclass(frozen=True, repr=False)
class LLMEndpointSettings(_SafeRepr):
    """One OpenAI-compatible chat endpoint in a provider chain."""

    name: str
    base_url: str
    api_key: str
    model: str
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    # True when the model came from a per-endpoint variable (GROQ_MODEL,
    # OPENROUTER_MODEL, LLM_CUSTOM_<N>_MODEL) rather than the global LLM model,
    # so callers that switch the global model at runtime keep the override.
    model_overridden: bool = False


@dataclass(frozen=True, repr=False)
class LLMSettings(_SafeRepr):
    provider: str
    model: str
    temperature: float
    max_new_tokens: int
    request_timeout: float
    total_timeout: float
    base_url: str
    api_key: str
    provider_order: Tuple[str, ...]
    endpoints: Tuple[LLMEndpointSettings, ...]
    presets: Mapping[str, Tuple[LLMEndpointSettings, ...]]
    local_model_path: str
    local_n_ctx: int
    local_n_gpu_layers: int

    def chain(self, order: Sequence[str]) -> Tuple[LLMEndpointSettings, ...]:
        """Resolve an ordered provider list (presets and custom_N) to endpoints."""
        resolved: List[LLMEndpointSettings] = []
        for name in order:
            resolved.extend(self.presets.get(str(name).strip().lower(), ()))
        return tuple(resolved)


@dataclass(frozen=True, repr=False)
class EmbeddingSettings(_SafeRepr):
    provider: str
    model: str
    base_url: str
    api_key: str
    device: str
    local_backend: str
    batch_size: int
    huggingface_token: str


@dataclass(frozen=True, repr=False)
class RerankerSettings(_SafeRepr):
    enabled: bool
    type: str
    model: str
    base_url: str
    api_key: str
    api_style: str
    device: str
    top_k: int
    rerank_top_k: int
    timeout: float
    pinecone_api_key: str


@dataclass(frozen=True, repr=False)
class VisionSettings(_SafeRepr):
    enable_image_extraction: bool
    enable_vision_captioning: bool
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True, repr=False)
class VectorStoreSettings(_SafeRepr):
    # Chroma client telemetry (PostHog). Off unless explicitly enabled, so
    # self-hosted and air-gapped deployments never phone home.
    anonymized_telemetry: bool


@dataclass(frozen=True, repr=False)
class PromptSettings(_SafeRepr):
    language: str


@dataclass(frozen=True, repr=False)
class LockSettings(_SafeRepr):
    enabled: bool
    redis_url: str
    prefix: str
    ttl_seconds: int
    wait_seconds: int


@dataclass(frozen=True, repr=False)
class APISettings(_SafeRepr):
    host: str
    port: int
    auth_token: str
    max_upload_size_mb: int
    instance_id: str


@dataclass(frozen=True, repr=False)
class LoggingSettings(_SafeRepr):
    level: str
    to_file: bool


@dataclass(frozen=True, repr=False)
class ClientSettings(_SafeRepr):
    """Settings for API clients such as the CLI (``python -m src.cli``)."""

    api_url: str
    api_token: str


@dataclass(frozen=True, repr=False)
class Settings(_SafeRepr):
    llm: LLMSettings
    embeddings: EmbeddingSettings
    reranker: RerankerSettings
    vision: VisionSettings
    vectorstore: VectorStoreSettings
    prompt: PromptSettings
    locks: LockSettings
    api: APISettings
    logging: LoggingSettings
    client: ClientSettings
    raw: Mapping[str, Any]


class _EnvReader:
    """Typed accessors over an env mapping and the resolved YAML config."""

    def __init__(self, env: Mapping[str, str], raw: Mapping[str, Any]):
        self.env = env
        self.raw = raw

    @staticmethod
    def _is_blank(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    def value(self, var: str, default: Any = None, yaml_path: Sequence[str] = ()) -> Any:
        """YAML value (already env-resolved) when the key exists, else env, else default."""
        if yaml_path:
            node: Any = self.raw
            for key in yaml_path:
                if not isinstance(node, Mapping) or key not in node:
                    node = _MISSING
                    break
                node = node[key]
            if node is not _MISSING and not self._is_blank(node):
                return node
        raw_env = self.env.get(var)
        if not self._is_blank(raw_env):
            return raw_env
        return default

    def str(self, var: str, default: str = "", yaml_path: Sequence[str] = ()) -> str:
        value = self.value(var, default, yaml_path)
        return "" if value is None else str(value).strip()

    def bool(self, var: str, default: bool, yaml_path: Sequence[str] = ()) -> bool:
        value = self.value(var, default, yaml_path)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        lowered = str(value).strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
        raise ConfigError(f"{var} must be a boolean (true/false), got {value!r}")

    def int(self, var: str, default: int, yaml_path: Sequence[str] = (), minimum: int = None) -> int:
        value = self.value(var, default, yaml_path)
        try:
            number = int(value) if not isinstance(value, float) or value.is_integer() else None
            if number is None:
                raise ValueError
        except (TypeError, ValueError):
            raise ConfigError(f"{var} must be an integer, got {value!r}") from None
        return max(minimum, number) if minimum is not None else number

    def float(self, var: str, default: float, yaml_path: Sequence[str] = (), minimum: float = None) -> float:
        value = self.value(var, default, yaml_path)
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ConfigError(f"{var} must be a number, got {value!r}") from None
        if number != number or number in (float("inf"), float("-inf")):
            raise ConfigError(f"{var} must be a finite number, got {value!r}")
        return max(minimum, number) if minimum is not None else number

    def choice(
        self,
        var: str,
        default: str,
        allowed: Sequence[str],
        yaml_path: Sequence[str] = (),
        aliases: Mapping[str, str] = None,
    ) -> str:
        value = self.str(var, default, yaml_path).lower()
        value = (aliases or {}).get(value, value)
        if value not in allowed:
            raise ConfigError(f"{var} must be one of {', '.join(allowed)}; got {value!r}")
        return value


_LLM_PROVIDERS = ("provider_chain", "openai_compatible", "local", "groq", "openrouter", "huggingface")
_LLM_PROVIDER_ALIASES = {"chain": "provider_chain", "auto": "provider_chain", "openai": "openai_compatible"}
_CUSTOM_ENDPOINT_RE = re.compile(r"^custom_(\d+)$")
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_HUGGINGFACE_ROUTER_URL = "https://router.huggingface.co/v1"


def _numbered_key_endpoints(
    reader: _EnvReader,
    provider: str,
    base_url: str,
    key_prefix: str,
    model: str,
    max_index: int,
    extra_headers: Mapping[str, str] = None,
    model_overridden: bool = False,
) -> Tuple[LLMEndpointSettings, ...]:
    """Expand KEY, KEY_1..KEY_<max_index> exactly like the legacy provider chain."""
    endpoints = []
    for env_name in [key_prefix] + [f"{key_prefix}_{idx}" for idx in range(1, max_index + 1)]:
        api_key = reader.str(env_name)
        if not api_key:
            continue
        suffix = env_name[len(key_prefix):].lstrip("_")
        endpoints.append(LLMEndpointSettings(
            name=f"{provider}{suffix}",
            base_url=base_url,
            api_key=api_key,
            model=model,
            extra_headers=MappingProxyType(dict(extra_headers or {})),
            model_overridden=model_overridden,
        ))
    return tuple(endpoints)


def _build_llm_settings(reader: _EnvReader) -> LLMSettings:
    provider = reader.choice("LLM_PROVIDER", "provider_chain", _LLM_PROVIDERS,
                             ("llm", "provider"), _LLM_PROVIDER_ALIASES)
    model = reader.str("LLM_MODEL", "openai/gpt-oss-120b", ("llm", "model_name"))
    request_timeout = reader.float("LLM_REQUEST_TIMEOUT", 60.0, minimum=1.0)
    total_timeout = max(request_timeout, reader.float("LLM_TOTAL_TIMEOUT", 110.0))

    raw_order = reader.str("LLM_PROVIDER_ORDER", "groq,openrouter")
    provider_order = tuple(item.strip().lower() for item in raw_order.split(",") if item.strip())
    provider_order = provider_order or ("groq", "openrouter")

    groq_model = reader.str("GROQ_MODEL")
    openrouter_model = reader.str("OPENROUTER_MODEL")
    presets: Dict[str, Tuple[LLMEndpointSettings, ...]] = {
        "groq": _numbered_key_endpoints(
            reader, "groq", _GROQ_BASE_URL, "GROQ_API_KEY",
            groq_model or model,
            reader.int("GROQ_KEY_MAX_INDEX", 6, minimum=0),
            model_overridden=bool(groq_model),
        ),
        "openrouter": _numbered_key_endpoints(
            reader, "openrouter", _OPENROUTER_BASE_URL, "OPENROUTER_API_KEY",
            openrouter_model or model,
            reader.int("OPENROUTER_KEY_MAX_INDEX", 7, minimum=0),
            extra_headers={
                "HTTP-Referer": reader.str("OPENROUTER_SITE_URL", "http://localhost"),
                "X-Title": reader.str("OPENROUTER_APP_NAME", "RAG Essay Grading API"),
            },
            model_overridden=bool(openrouter_model),
        ),
    }
    hf_token = reader.str("HUGGINGFACE_API_TOKEN")
    presets["huggingface"] = (
        (LLMEndpointSettings("huggingface", _HUGGINGFACE_ROUTER_URL, hf_token, model,
                             MappingProxyType({})),)
        if hf_token else ()
    )

    for name in provider_order:
        match = _CUSTOM_ENDPOINT_RE.match(name)
        if match:
            prefix = f"LLM_CUSTOM_{match.group(1)}"
            base_url = reader.str(f"{prefix}_BASE_URL")
            if not base_url:
                raise ConfigError(f"{prefix}_BASE_URL is required because LLM_PROVIDER_ORDER lists {name}")
            custom_model = reader.str(f"{prefix}_MODEL")
            presets[name] = (LLMEndpointSettings(
                name=name,
                base_url=base_url,
                api_key=reader.str(f"{prefix}_API_KEY"),
                model=custom_model or model,
                extra_headers=MappingProxyType({}),
                model_overridden=bool(custom_model),
            ),)
        elif name not in presets:
            logger.warning(f"Skipping unknown provider in LLM_PROVIDER_ORDER: {name}")

    frozen_presets = MappingProxyType(presets)
    settings = LLMSettings(
        provider=provider,
        model=model,
        temperature=reader.float("LLM_TEMPERATURE", 0.3, ("llm", "temperature"), minimum=0.0),
        max_new_tokens=reader.int("LLM_MAX_NEW_TOKENS", 2048, ("llm", "max_new_tokens"), minimum=1),
        request_timeout=request_timeout,
        total_timeout=total_timeout,
        base_url=reader.str("LLM_BASE_URL"),
        api_key=reader.str("LLM_API_KEY"),
        provider_order=provider_order,
        endpoints=(),
        presets=frozen_presets,
        local_model_path=reader.str("LLM_LOCAL_MODEL_PATH"),
        local_n_ctx=reader.int("LLM_LOCAL_N_CTX", 4096, minimum=512),
        local_n_gpu_layers=reader.int("LLM_LOCAL_N_GPU_LAYERS", 0, minimum=-1),
    )
    # dataclasses.replace keeps the instance frozen while filling the resolved chain.
    return replace(settings, endpoints=settings.chain(provider_order))


_DEVICE_ALIASES = {"cloud": "cpu", "gpu": "cuda"}


def _build_settings(reader: _EnvReader) -> Settings:
    hf_token = reader.str("HUGGINGFACE_API_TOKEN")

    embeddings = EmbeddingSettings(
        provider=reader.choice("EMBEDDING_PROVIDER", "huggingface",
                               ("huggingface", "openai_compatible", "local"),
                               aliases={"hf": "huggingface", "openai": "openai_compatible"}),
        model=reader.str("EMBEDDING_MODEL", "BAAI/bge-m3", ("embeddings", "model_name")),
        base_url=reader.str("EMBEDDING_BASE_URL"),
        api_key=reader.str("EMBEDDING_API_KEY"),
        device=reader.choice("EMBEDDING_DEVICE", "cpu", ("cpu", "cuda", "mps"),
                             ("embeddings", "device"), _DEVICE_ALIASES),
        local_backend=reader.choice("EMBEDDING_LOCAL_BACKEND", "fastembed",
                                    ("fastembed", "sentence_transformers"),
                                    aliases={"sentence-transformers": "sentence_transformers"}),
        batch_size=reader.int("EMBEDDING_BATCH_SIZE", 64, minimum=1),
        huggingface_token=hf_token,
    )

    reranker = RerankerSettings(
        enabled=reader.bool("ENABLE_RERANKING", False, ("retrieval", "enable_reranking")),
        type=reader.choice("RERANKER_TYPE", "pinecone",
                           ("none", "bm25", "local_cross_encoder", "http_rerank", "llm_rerank", "pinecone"),
                           ("retrieval", "reranker_type"),
                           {"bge": "pinecone", "disabled": "none", "cross_encoder": "local_cross_encoder"}),
        model=reader.str("RERANKER_MODEL", "bge-reranker-v2-m3", ("retrieval", "reranker_model")),
        base_url=reader.str("RERANKER_BASE_URL"),
        api_key=reader.str("RERANKER_API_KEY"),
        api_style=reader.choice("RERANKER_API_STYLE", "cohere", ("cohere", "tei")),
        device=reader.choice("RERANKER_DEVICE", "cpu", ("cpu", "cuda", "mps"), aliases=_DEVICE_ALIASES),
        top_k=reader.int("RETRIEVAL_TOP_K", 5, ("retrieval", "top_k"), minimum=1),
        rerank_top_k=reader.int("RERANK_TOP_K", 3, ("retrieval", "rerank_top_k"), minimum=1),
        timeout=reader.float("RERANKER_TIMEOUT", 30.0, minimum=1.0),
        pinecone_api_key=reader.str("PINECONE_API_KEY"),
    )

    vision = VisionSettings(
        enable_image_extraction=reader.bool("ENABLE_IMAGE_EXTRACTION", False,
                                            ("multimodal", "enable_image_extraction")),
        enable_vision_captioning=reader.bool("ENABLE_VISION_CAPTIONING", False,
                                             ("multimodal", "enable_vision_captioning")),
        base_url=reader.str("VISION_BASE_URL", _HUGGINGFACE_ROUTER_URL),
        api_key=reader.str("VISION_API_KEY", hf_token),
        model=reader.str("VISION_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
    )

    locks = LockSettings(
        enabled=reader.bool("DISTRIBUTED_LOCK_ENABLED", False),
        redis_url=reader.str("REDIS_URL", "redis://redis:6379/0"),
        prefix=reader.str("DISTRIBUTED_LOCK_PREFIX", "airag:lock"),
        ttl_seconds=reader.int("DISTRIBUTED_LOCK_TTL_SECONDS", 900, minimum=60),
        wait_seconds=reader.int("DISTRIBUTED_LOCK_WAIT_SECONDS", 120, minimum=1),
    )

    api = APISettings(
        host=reader.str("API_HOST", "0.0.0.0", ("api", "host")),
        port=reader.int("API_PORT", 8000, ("api", "port"), minimum=1),
        auth_token=reader.str("API_AUTH_TOKEN"),
        max_upload_size_mb=reader.int("MAX_UPLOAD_SIZE_MB", 50, minimum=1),
        instance_id=reader.str("HOSTNAME") or socket.gethostname(),
    )

    return Settings(
        llm=_build_llm_settings(reader),
        embeddings=embeddings,
        reranker=reranker,
        vision=vision,
        vectorstore=VectorStoreSettings(
            anonymized_telemetry=reader.bool("ANONYMIZED_TELEMETRY", False),
        ),
        prompt=PromptSettings(
            language=reader.choice("PROMPT_LANGUAGE", "auto", ("auto", "en", "id")),
        ),
        locks=locks,
        api=api,
        logging=LoggingSettings(
            level=reader.str("LOG_LEVEL", "INFO").upper(),
            to_file=reader.bool("LOG_TO_FILE", True),
        ),
        client=ClientSettings(
            api_url=reader.str("RAG_API_URL", "http://127.0.0.1:8000").rstrip("/"),
            # On the API host the server token is the natural default.
            api_token=reader.str("RAG_API_TOKEN") or api.auth_token,
        ),
        raw=MappingProxyType(reader.raw),
    )


def load_settings(env: Mapping[str, str] = None, config_path: Path = None) -> Settings:
    """Build settings from ``env`` (default: os.environ) and config.yaml.

    Raises:
        ConfigError: if any value is invalid; the message names the variable.
    """
    source: Mapping[str, str] = dict(os.environ) if env is None else dict(env)
    try:
        raw = _read_yaml_config(config_path, source)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return _build_settings(_EnvReader(source, raw))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once from the environment."""
    return load_settings()


def reset_settings() -> None:
    """Drop cached settings so the next get_settings() re-reads the environment."""
    get_settings.cache_clear()


@contextmanager
def override_settings(**env: Optional[str]) -> Iterator[Settings]:
    """Temporarily set (or unset with ``None``) env vars and reload settings.

    Intended for tests; restores the previous environment and cache on exit.
    """
    previous = {name: os.environ.get(name) for name in env}
    try:
        for name, value in env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = str(value)
        reset_settings()
        yield get_settings()
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        reset_settings()
