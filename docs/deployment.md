# Production Deployment Guide

## 1. Prerequisites

- Linux host with Docker Engine and Docker Compose plugin (`docker compose version`)
- Network reachability between the Moodle server and the backend API port (`8000/tcp`)
- Provider API keys:
  - `HUGGINGFACE_API_TOKEN` (used for `BAAI/bge-m3` embeddings)
  - `GROQ_API_KEY` and/or `OPENROUTER_API_KEY` (LLM provider chain)
  - Optional `PINECONE_API_KEY` (only required if `ENABLE_RERANKING=true` with `RERANKER_TYPE=bge`)

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

