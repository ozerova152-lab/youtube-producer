"""Общие заготовки тестов: копия демо-канала во временной папке."""

import shutil
from pathlib import Path

import pytest

DEMO = Path(__file__).parent.parent / "examples" / "demo"


@pytest.fixture
def channel(tmp_path) -> Path:
    """Копия examples/demo в tmp_path/<канал>; рядом лежит общий учёт квоты."""
    dest = tmp_path / "chan"
    shutil.copytree(DEMO, dest)
    # Свой канал, как в инструкции: строку `fixed_date` (только для демо) пользователь удаляет;
    # вне папки demo она игнорируется с предупреждением, которое попало бы в вывод команд.
    settings = dest / "settings.yaml"
    settings.write_text("".join(line for line in settings.read_text(encoding="utf-8").splitlines(keepends=True)
                                if not line.startswith("fixed_date:")), encoding="utf-8")
    return dest


@pytest.fixture(scope="module")
def vcr_cassette_dir() -> str:
    return str(DEMO / "cassettes")


@pytest.fixture(scope="module")
def vcr_config() -> dict:
    # Ключ и дата начала периода меняются от запуска к запуску: в кассете их нет,
    # при сопоставлении запросов они тоже отбрасываются.
    return {"filter_query_parameters": ["key", "publishedAfter"], "record_mode": "none"}
