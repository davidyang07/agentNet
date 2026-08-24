.PHONY: dev test lint types verify-determinism

dev:
	docker compose up --build

test:
	cd backend && .venv/bin/pytest

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
