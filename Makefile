VENV := .venv
BIN := $(VENV)/bin

.PHONY: setup check reset secrets cassettes

setup:
	python3 -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e ".[dev]"
	$(BIN)/playwright install chromium

check: secrets cassettes
	$(BIN)/ruff check src tests
	$(BIN)/pytest -q

secrets:
	gitleaks detect --no-git --source . --config .gitleaks.toml --no-banner
	@if git rev-parse HEAD >/dev/null 2>&1; then \
		gitleaks detect --source . --config .gitleaks.toml --no-banner; \
	fi

cassettes:
	$(BIN)/python -m produce.core.cassettes examples/demo/cassettes

reset:
	rm -rf data/demo
	@echo "Тестовый канал сброшен: data/demo удалена"
