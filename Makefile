.PHONY: dev test lint types verify-determinism migrate

dev:
	docker compose up --build

# Backend tests hit a real Postgres (persistence integration tests) -- run
# against a dedicated agentnet_test database, created if absent, so the
# suite never touches dev data. Requires `docker compose up postgres` (or an
# equivalent local Postgres) already running and reachable via the
# POSTGRES_* env vars (defaults: localhost:5432, user/password agentnet).
test:
	PGPASSWORD=$${POSTGRES_PASSWORD:-agentnet_dev} psql -h $${POSTGRES_HOST:-localhost} -p $${POSTGRES_PORT:-5432} -U $${POSTGRES_USER:-agentnet} -tc "SELECT 1 FROM pg_database WHERE datname = 'agentnet_test'" | grep -q 1 || \
	PGPASSWORD=$${POSTGRES_PASSWORD:-agentnet_dev} createdb -h $${POSTGRES_HOST:-localhost} -p $${POSTGRES_PORT:-5432} -U $${POSTGRES_USER:-agentnet} agentnet_test
	cd backend && POSTGRES_DB=agentnet_test .venv/bin/pytest

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run lint
	cd frontend && npx tsc --noEmit

# Requires a backend already running at localhost:8000 (e.g. `make dev`, or
# `cd backend && .venv/bin/uvicorn app.main:app`).
types:
	cd frontend && npx openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts

verify-determinism:
	cd backend && .venv/bin/python scripts/verify_determinism.py

# Applies pending migrations standalone, without booting the full app.
migrate:
	cd backend && .venv/bin/python scripts/migrate.py
