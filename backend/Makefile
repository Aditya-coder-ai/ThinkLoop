.PHONY: up down lint format types test migrate migrate-down content-validate content-sync eval-retrieval eval-flashcards eval-videos sim-battle verify

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

content-validate:
	uv run python -m app.content.cli validate --strict

content-sync:
	uv run python -m app.content.cli sync

eval-retrieval:
	uv run python evals/run_retrieval_eval.py --embedder fake

eval-flashcards:
	uv run python evals/run_flashcard_eval.py --mode fake

eval-videos:
	uv run python evals/run_video_eval.py --mode fake

sim-battle:
	uv run python evals/run_battle_sim.py --battles 100

verify: lint types test
	uv run python -m scripts.verify_migrations
	$(MAKE) content-validate
	$(MAKE) eval-retrieval
	$(MAKE) eval-flashcards
	$(MAKE) eval-videos
	$(MAKE) sim-battle
