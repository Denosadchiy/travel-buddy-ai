# Makefile for Trip Planning API

.PHONY: help install dev up down logs db-migrate db-upgrade db-downgrade seed-pois test clean check-externals check-llm check-google-places check-google-routes

help:
	@echo "Trip Planning API - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install            - Install Python dependencies"
	@echo "  make dev                - Run API locally (without Docker)"
	@echo "  make up                 - Start Docker containers (API + PostgreSQL)"
	@echo "  make down               - Stop Docker containers"
	@echo "  make logs               - View Docker container logs"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate         - Generate new Alembic migration"
	@echo "  make db-upgrade         - Apply database migrations"
	@echo "  make db-downgrade       - Rollback last migration"
	@echo "  make seed-pois          - Seed database with example POIs"
	@echo ""
	@echo "Testing:"
	@echo "  make test               - Run tests with pytest"
	@echo "  make check-externals    - Check all external service integrations"
	@echo "  make check-llm          - Check LLM / IO.NET connectivity"
	@echo "  make check-google-places - Check Google Places API"
	@echo "  make check-google-routes - Check Google Routes API"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean              - Clean up generated files"

install:
	pip install -r requirements.txt

dev:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

db-migrate:
	alembic revision --autogenerate -m "$(msg)"

db-upgrade:
	alembic upgrade head

db-downgrade:
	alembic downgrade -1

seed-pois:
	python -m scripts.seed_pois

test:
	pytest tests/ -v

# External service integration checks (manual, not part of pytest suite)
check-externals:
	@echo "============================================"
	@echo "Checking External Service Integrations"
	@echo "============================================"
	@echo ""
	@python -m scripts.check_llm_ionet && \
	echo "" && \
	python -m scripts.check_google_places && \
	echo "" && \
	python -m scripts.check_google_routes && \
	echo "" && \
	echo "============================================" && \
	echo "✅ All external service checks passed!" && \
	echo "============================================"

check-llm:
	python -m scripts.check_llm_ionet

check-google-places:
	python -m scripts.check_google_places

check-google-routes:
	python -m scripts.check_google_routes

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
