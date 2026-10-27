"""Настройки канала (`settings.yaml`) и ключ YouTube из `.env`."""

import os
from pathlib import Path

import yaml

from produce.core.errors import ProduceError

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


def load_api_key(env_path: Path = Path(".env")) -> str | None:
    """Ключ YouTube: из переменной окружения или из `.env`. None, если ключа нет.

    Значение наружу не печатается и в логи не пишется; вызывающий код проверяет
    только «есть или нет».
    """
    value = os.environ.get(KEY_NAME, "").strip()
    if not value and env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            name, sep, raw = line.partition("=")
            if sep and name.strip() == KEY_NAME:
                value = raw.strip().strip("'\"")
                break
    return value or None
