FROM python:3.12-slim

WORKDIR /app

ARG APP_UID=10001
ARG APP_GID=10001

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
# Optional extras (both default to false to keep the image lean):
#   INSTALL_LOCAL_EXTRAS=true    -> requirements-local.txt (fastembed; local embeddings/reranking)
#   INSTALL_OPTIONAL_EXTRAS=true -> requirements-optional.txt (Pinecone reranking)
ARG INSTALL_LOCAL_EXTRAS=false
ARG INSTALL_OPTIONAL_EXTRAS=false

COPY requirements.txt requirements-local.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_LOCAL_EXTRAS" = "true" ]; then pip install --no-cache-dir -r requirements-local.txt; fi \
    && if [ "$INSTALL_OPTIONAL_EXTRAS" = "true" ]; then pip install --no-cache-dir -r requirements-optional.txt; fi

# Model caches for local providers (fastembed / sentence-transformers).
ENV HF_HOME=/app/data/models/huggingface \
    FASTEMBED_CACHE_PATH=/app/data/models/fastembed

RUN groupadd --gid ${APP_GID} app \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home app

COPY --chown=app:app . .

RUN mkdir -p data/chroma_db data/uploads data/models logs \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--timeout", "600", "--graceful-timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "src.api.app:app"]
