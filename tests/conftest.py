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
    return dest
