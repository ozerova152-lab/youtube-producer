"""Настройки канала (`settings.yaml`) и ключ YouTube из `.env`."""

import os
from datetime import date
from pathlib import Path

import yaml

from produce.core.errors import ProduceError
from produce.core.files import write_text_atomic

KEY_NAME = "YOUTUBE_API_KEY"


class SettingsError(ProduceError):
    """Файл настроек не найден или неразборчив."""


def load_settings(channel_dir: Path) -> dict:
    path = channel_dir / "settings.yaml"
    if not path.exists():
        raise SettingsError(f"Не найден файл настроек: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        mark = getattr(err, "problem_mark", None)
        place = f" (строка {mark.line + 1}, столбец {mark.column + 1})" if mark else ""
        raise SettingsError(f"Не удалось прочитать {path}{place}. Файл не изменён") from err
    if not isinstance(data, dict) or not data.get("segments"):
        raise SettingsError(f"В {path} нет раздела segments")
    segments = data["segments"]
    if not isinstance(segments, list) or not all(
        isinstance(s, dict) and s.get("id") for s in segments
    ):
        raise SettingsError(f"В {path} у каждого сегмента должно быть поле id")
    ids = [str(s["id"]) for s in segments]
    if len(set(ids)) != len(ids):
        raise SettingsError(f"В {path} id сегментов повторяются")
    return data


DEMO_DIR_NAME = "demo"
FIXED_DATE_IGNORED = (
    "`fixed_date` игнорируется: это не демо-канал. Удалите строку из settings.yaml"
)


def apply_fixed_date(channel_dir: Path) -> tuple[str | None, str | None]:
    """Демо-канал: `fixed_date` в `settings.yaml` замораживает «сегодня» (через `PRODUCE_NOW`).

    Нужна, чтобы тестовый канал давал один и тот же результат в любой день: залёты демо старше
    30 дней перестали бы быть залётами. Действует только в папке `demo` (`data/demo`): строка,
    случайно скопированная в свой канал, заморозила бы ему даты, поэтому там она игнорируется
    с предупреждением. Заданная `PRODUCE_NOW` сильнее. Возвращает (дата, предупреждение).
    """
    if os.environ.get("PRODUCE_NOW", "").strip():
        return None, None
    try:
        data = load_settings(channel_dir)
    except SettingsError:
        return None, None  # о проблемах файла настроек скажет сама команда
    value = data.get("fixed_date")
    if value is None:
        return None, None
    if channel_dir.resolve().name != DEMO_DIR_NAME:
        return None, FIXED_DATE_IGNORED
    try:
        day = date.fromisoformat(str(value).strip())
    except ValueError as err:
        raise SettingsError(
            "В `settings.yaml` поле `fixed_date` должно быть датой ГГГГ-ММ-ДД. Исправьте и повторите"
        ) from err
    os.environ["PRODUCE_NOW"] = day.isoformat()
    return day.isoformat(), None


def list_segments(settings: dict) -> list[dict]:
    return list(settings["segments"])


def get_segment(settings: dict, segment_id: str) -> dict:
    for segment in settings["segments"]:
        if str(segment["id"]) == segment_id:
            return segment
    known = ", ".join(str(s["id"]) for s in settings["segments"])
    raise SettingsError(f"Сегмента «{segment_id}» нет в настройках. Есть: {known}")


def my_channel_id(settings: dict) -> str | None:
    """Мой канал из `channel.my_channel_id`; None, если не задан (пусто или нет поля)."""
    section = settings.get("channel")
    value = section.get("my_channel_id") if isinstance(section, dict) else None
    text = str(value).strip() if value is not None else ""
    return text or None


def read_env_key(env_path: Path = Path(".env")) -> str | None:
    """Ключ только из файла `.env` (без переменной окружения). Значение наружу не печатается."""
    if not env_path.is_file():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        name, sep, raw = line.partition("=")
        if sep and name.strip() == KEY_NAME:
            return raw.strip().strip("'\"") or None
    return None


def load_api_key(env_path: Path = Path(".env")) -> str | None:
    """Ключ YouTube: из переменной окружения или из `.env`. None, если ключа нет.

    Значение наружу не печатается и в логи не пишется; вызывающий код проверяет
    только «есть или нет».
    """
    return os.environ.get(KEY_NAME, "").strip() or read_env_key(env_path)


def save_api_key(value: str, env_path: Path = Path(".env")) -> bool:
    """Записывает ключ в `.env` с правами только для владельца; True, если заменён прежний.

    Остальные строки файла не трогаются. Значение не попадает ни в сообщения об ошибках,
    ни в логи: ошибка называет только причину.
    """
    key = value.strip()
    if not key or any(ch.isspace() or ch in "'\"" for ch in key):
        raise ProduceError("Ключ пустой или в нём есть пробелы или кавычки. Ключ не записан")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
    replaced = False
    for n, line in enumerate(lines):
        name, sep, _ = line.partition("=")
        if sep and name.strip() == KEY_NAME:
            lines[n] = f"{KEY_NAME}={key}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{KEY_NAME}={key}")
    write_text_atomic(env_path, "\n".join(lines) + "\n")
    env_path.chmod(0o600)  # временный файл и так закрыт для других; здесь страховка для уже существовавшего
    return replaced
