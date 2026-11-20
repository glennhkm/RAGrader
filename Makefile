.PHONY: help test lint-php build-plugins up down logs clean

PYTHON ?= python3

help:
	@echo "Available targets:"
	@echo "  make test           Run backend Python unit tests (network access blocked)"
	@echo "  make lint-php       Syntax-check all Moodle plugin PHP files"
	@echo "  make build-plugins  Build Moodle-installable ZIP archives into dist/"
	@echo "  make up             Start backend Docker Compose stack (API, Chroma, Redis, HAProxy)"
	@echo "  make down           Stop backend Docker Compose stack"
	@echo "  make logs           Tail backend Docker Compose logs"
	@echo "  make clean          Remove generated dist/ plugin archives"

test:
	cd backend && $(PYTHON) tests/run_offline.py -v

lint-php:
	find moodle-plugins -name "*.php" -print0 | xargs -0 -n1 php -l

build-plugins:
	./scripts/build-plugins.sh

up:
	cd backend && docker compose up -d --build --remove-orphans

down:
	cd backend && docker compose down

logs:
	cd backend && docker compose logs -f --tail=100 api chroma redis load-balancer

clean:
	rm -rf dist

