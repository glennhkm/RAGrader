# Production Deployment Guide

## 1. Prerequisites

- Linux host with Docker Engine and Docker Compose plugin (`docker compose version`)
- Network reachability between the Moodle server and the backend API port (`8000/tcp`)
- Model providers — either the cloud defaults or your own endpoints (see [section 6](#6-model-providers)):
  - Defaults: `GROQ_API_KEY` and/or `OPENROUTER_API_KEY` (LLM chain) and `HUGGINGFACE_API_TOKEN` (`BAAI/bge-m3` embeddings)
  - Optional `PINECONE_API_KEY` (only for `ENABLE_RERANKING=true` with `RERANKER_TYPE=pinecone`, legacy `bge`)
  - No cloud key is required when every stage points at OpenAI-compatible or local models

## 2. Configure Environment

```bash
cd backend
cp .env.example .env
chmod 600 .env
```

Recommended production values in `backend/.env`:

```dotenv
ENVIRONMENT=production
API_BIND_ADDRESS=<BACKEND_PRIVATE_OR_LAN_IP>
API_HOST=0.0.0.0
API_PORT=8000
API_REPLICAS=2
MAX_UPLOAD_SIZE_MB=50
API_AUTH_TOKEN=<STRONG_RANDOM_BEARER_TOKEN>
LOG_TO_FILE=false

CHROMA_CLIENT_MODE=http
CHROMA_HOST=chroma
CHROMA_PORT=8000
CHROMA_SSL=false

REDIS_URL=redis://redis:6379/0
DISTRIBUTED_LOCK_ENABLED=true
DISTRIBUTED_LOCK_TTL_SECONDS=900
DISTRIBUTED_LOCK_WAIT_SECONDS=120

LLM_PROVIDER=provider_chain
LLM_PROVIDER_ORDER=groq,openrouter
LLM_REQUEST_TIMEOUT=60
LLM_TOTAL_TIMEOUT=110
GROQ_API_KEY=<SECRET>
OPENROUTER_API_KEY=<SECRET>
HUGGINGFACE_API_TOKEN=<SECRET>

ENABLE_RERANKING=false
ENABLE_IMAGE_EXTRACTION=false
ENABLE_VISION_CAPTIONING=false
```

## 3. Permissions & Startup

API and Chroma containers run as UID/GID `10001`:

```bash
cd backend
mkdir -p data/chroma_db data/uploads logs
sudo chown -R 10001:10001 data logs
docker compose config --quiet
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
```

Expected running services: 2 `api` replicas (or `API_REPLICAS`), 1 `chroma`, 1 `redis`, and 1 `load-balancer`. Only `load-balancer` publishes port `8000`.

## 4. Firewall & Verification

Allow TCP port `8000` **only** from your Moodle server's source IP. Then verify:

```bash
curl -fsS http://<BACKEND_IP>:8000/health
curl -fsS -H "Authorization: Bearer <API_AUTH_TOKEN>" http://<BACKEND_IP>:8000/moodle/status
```

Verify load balancing across replicas by inspecting the `X-API-Instance` response header across multiple `/health` requests.

## 5. Backups

Before backing up `backend/data/chroma_db`, stop writers first so Chroma's files are quiescent:

```bash
cd backend
docker compose down
tar -czf "rag-data-$(date +%Y%m%d-%H%M%S).tar.gz" data
docker compose up -d
```

## 6. Model Providers

All provider settings live in `backend/.env` (documented in `backend/.env.example`). Model ids are passed through unchanged. Invalid values stop the API at startup with a message naming the variable.

### LLM

```dotenv
# Ollama / vLLM / LM Studio / llama.cpp server / LiteLLM / OpenAI (one endpoint)
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://ollama:11434/v1        # vLLM: http://vllm:8000/v1, OpenAI: https://api.openai.com/v1
LLM_API_KEY=                               # optional for self-hosted servers
LLM_MODEL=qwen2.5:14b-instruct

# Or a fallback chain mixing presets and your own endpoints
LLM_PROVIDER=provider_chain
LLM_PROVIDER_ORDER=custom_1,groq,openrouter
LLM_CUSTOM_1_BASE_URL=http://vllm:8000/v1
LLM_CUSTOM_1_MODEL=Qwen/Qwen2.5-14B-Instruct
LLM_REQUEST_TIMEOUT=60                     # per endpoint attempt
LLM_TOTAL_TIMEOUT=110                      # whole chain
```

`LLM_PROVIDER=local` runs a GGUF model in-process (`LLM_LOCAL_MODEL_PATH`; build with `INSTALL_LOCAL_EXTRAS=true` and enable `llama-cpp-python` in `requirements-local.txt`). For multi-replica deployments prefer a shared Ollama/vLLM server.

### Embeddings

```dotenv
EMBEDDING_PROVIDER=openai_compatible       # or huggingface (default) / local
EMBEDDING_BASE_URL=http://ollama:11434/v1  # TEI: http://tei:8080/v1, OpenAI: https://api.openai.com/v1
EMBEDDING_MODEL=bge-m3
```

`EMBEDDING_PROVIDER=local` embeds in-process with fastembed (`INSTALL_LOCAL_EXTRAS=true`) or `EMBEDDING_LOCAL_BACKEND=sentence_transformers`; `EMBEDDING_DEVICE=cuda` uses a GPU.

> **Changing embeddings on an existing deployment:** collections remember the embedding provider, model and dimension. Requests against a course built with a different setup return **HTTP 409**. Re-vectorize the materials (in Moodle: *Re-vectorize* on each AI RAG Material) after switching, or switch back.

### Reranking

```dotenv
ENABLE_RERANKING=true
RERANKER_TYPE=http_rerank                  # bm25 | local_cross_encoder | http_rerank | llm_rerank | pinecone | none
RERANKER_BASE_URL=http://tei-rerank:8080   # Jina/Cohere/vLLM: https://api.jina.ai/v1 etc.
RERANKER_API_STYLE=tei                     # cohere (default) or tei
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RETRIEVAL_TOP_K=10                         # candidates fetched before reranking
RERANK_TOP_K=4                             # passages passed to the LLM
```

If a reranker cannot start, the API falls back to BM25; if a rerank call fails, the original vector order is used.

### Prompt language and vision

```dotenv
PROMPT_LANGUAGE=auto                       # auto | en | id
ENABLE_VISION_CAPTIONING=false
VISION_BASE_URL=http://ollama:11434/v1
VISION_MODEL=llava:13b
```

### Optional Docker extras

```bash
INSTALL_LOCAL_EXTRAS=true docker compose build      # fastembed for local embeddings/reranking
INSTALL_OPTIONAL_EXTRAS=true docker compose build   # Pinecone SDK
```

## 7. Single-Container Dev Stack

`backend/docker-compose.dev.yml` runs one API container with embedded Chroma and no Redis/HAProxy (plus an optional pinned Ollama under `--profile local`). It is meant for evaluation and development only; see the README quickstart.

