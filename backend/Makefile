.PHONY: up down lint format types test migrate migrate-down verify

up:
	docker compose up -d postgres redis

down:
	docker compose down

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

types:
	uv run mypy --strict app

test:
	uv run pytest -q

migrate:
	uv run alembic upgrade head

migrate-down:
	uv run alembic downgrade base

verify: lint types test
	uv run python -m scripts.verify_migrations
