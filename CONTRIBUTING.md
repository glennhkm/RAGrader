# Contributing to Moodle RAG Essay Grader

Thank you for your interest in contributing!

## Development Setup

### Backend (`backend/`)
1. Create a Python 3.10+ virtual environment and install dependencies:
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Run the unit test suite:
   ```bash
   python tests/run_offline.py -v   # unit tests with network access blocked
   ```
3. Run the full-stack integration tests (compose: HAProxy, two API replicas, Chroma, Redis, with a stub LLM/embedding provider; needs Docker):
   ```bash
   cd backend
   cp .env.example .env
   mkdir -p data/chroma_db data/uploads && sudo chown -R 10001:10001 data/chroma_db data/uploads
   docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait
   RAG_IT_URL=http://127.0.0.1:8000 RAG_IT_TOKEN=ci-token RAG_IT_EXPECT_REPLICAS=2 \
     python -m unittest discover -s integration_tests -v
   docker compose -f docker-compose.yml -f docker-compose.ci.yml down -v
   ```
   The tests live in `backend/integration_tests/` (not `tests/`) and skip when `RAG_IT_URL` is unreachable.
   They also run in CI (job `integration`). Without Docker, point `RAG_IT_URL` at any API wired to
   `python -m uvicorn integration_tests.stub_ai:app --port 9000` and an HTTP Chroma server on port 18001.

### Moodle Plugins (`moodle-plugins/`)
1. Check PHP syntax across all plugin files:
   ```bash
   find moodle-plugins -name "*.php" -print0 | xargs -0 -n1 php -l
   ```
2. Build and verify the Moodle ZIP archives:
   ```bash
   ./scripts/build-plugins.sh
   ```

## Pull Request Guidelines
- Keep `backend/` changes MIT-compatible and `moodle-plugins/` changes GPL-3.0-or-later compatible (preserve Moodle GPL boilerplate headers in PHP files).
- Never commit `.env` files, API keys, student submissions, or runtime `data/` / `logs/` artifacts.
- Add or update unit tests in `backend/tests/` for any API, locking, vectorstore, or auth changes.
- Verify CI checks (`make test`, `make lint-php`, `make build-plugins`) pass locally before opening a pull request.

