"""Безопасное чтение и запись файлов данных.

Запись идёт через временный файл с переименованием: оборванная запись не портит
старый файл. Чтение при ошибке называет файл и место, ничего не перезаписывает.
"""

import json
import os
import tempfile
from pathlib import Path

from produce.core.errors import FileFormatError


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def write_json_atomic(path: Path, data: object) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> object:
    """Читает JSON; при ошибке бросает FileFormatError с файлом, строкой и столбцом."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        raise FileFormatError(f"Не найден файл: {path}") from err
    except (OSError, UnicodeDecodeError) as err:
        raise FileFormatError(f"Не удалось прочитать файл {path}: {err.__class__.__name__}") from err
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise FileFormatError(
            f"Файл {path} повреждён: ошибка формата JSON в строке {err.lineno}, "
            f"столбце {err.colno} ({err.msg}). Файл не изменён. "
            "Исправьте его вручную или удалите и повторите шаг"
        ) from err
