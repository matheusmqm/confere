SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help install db migrate dev test test-db lint fmt seed eval demo-reset check-db

help: ## Lista os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependências Python (uv) e do frontend (pnpm)
	uv sync --all-packages
	pnpm -C apps/web install

db: ## Sobe o Postgres local e espera o healthcheck
	docker compose up -d --wait db

migrate: ## Aplica as migrações Alembic (use DATABASE_URL_WORKER para escolher o banco)
	cd apps/api && uv run alembic upgrade head

dev: db migrate ## Banco + migrações + API, worker e web em paralelo (Ctrl+C encerra tudo)
	@uv run python -c "import confere_api.main" 2>/dev/null || { echo "ERRO: confere_api.main ainda não existe (a API é criada em outra tarefa)."; exit 1; }
	@trap 'kill 0' INT TERM EXIT; \
	uv run uvicorn confere_api.main:app --reload --port 8000 & \
	uv run python -m confere_api.worker & \
	pnpm -C apps/web dev & \
	wait

test: ## Roda os testes Python e do frontend
	uv run pytest
	pnpm -C apps/web test

test-db: ## Roda só os testes que precisam de Postgres (marcador db)
	uv run pytest -m db

lint: ## ruff, mypy, eslint e typecheck do frontend
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages apps
	pnpm -C apps/web lint
	pnpm -C apps/web typecheck

fmt: ## Formata o código (ruff + prettier)
	uv run ruff format .
	uv run ruff check --fix .
	pnpm -C apps/web exec prettier --write .

seed: ## Gera o dataset sintético (seed 42) e carrega no banco (CF-39/CF-41)
	uv run python -m confere_synth.cli gerar --seed 42 --saida data/seed42
	uv run python -m confere_api.seed --dados data/seed42

eval: ## Roda a avaliação no conjunto de teste e grava eval/relatorio.json
	uv run python eval/run.py --seed 42

demo-reset: ## Reseta o estado da demo na API local
	curl -X POST localhost:8000/demo/reset

check-db: ## Verifica a conexão e as extensões do banco (script da CF-6)
	@test -f infra/scripts/check-db.sh || { echo "ERRO: infra/scripts/check-db.sh não existe (CF-6 ainda não está no repositório)."; exit 1; }
	bash infra/scripts/check-db.sh
