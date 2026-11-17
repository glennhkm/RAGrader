FROM python:3.10-slim

WORKDIR /app

ARG APP_UID=10001
ARG APP_GID=10001

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid ${APP_GID} app \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home app

COPY --chown=app:app . .

RUN mkdir -p data/chroma_db data/uploads logs \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--timeout", "600", "--graceful-timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "src.api.app:app"]
