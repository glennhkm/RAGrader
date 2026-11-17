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
   python -m unittest discover -s tests -v
   ```

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

