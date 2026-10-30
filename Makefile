VENV := .venv
BIN := $(VENV)/bin

.PHONY: setup setup-dev check reset secrets cassettes audit

# Для пользователя: только то, что нужно для запуска `produce`. Браузер Chromium (около 120 МБ)
# нужен лишь для проверки страницы-витрины, поэтому здесь его нет.
setup:
	python3 -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e .

# Для разработчика: плюс линтер, тесты и Chromium для UI-теста витрины (`make check` целиком).
setup-dev: setup
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

# Известные уязвимости в установленных пакетах. Ходит в сеть, поэтому отдельно от `make check`.
audit:
	$(BIN)/pip-audit --skip-editable --progress-spinner off

reset:
	rm -rf data/demo
	@echo "Тестовый канал сброшен: data/demo удалена"
