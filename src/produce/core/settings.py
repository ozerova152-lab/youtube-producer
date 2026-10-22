from pathlib import Path

import yaml


class SettingsError(Exception):
    """Файл настроек не найден или неразборчив."""


def load_settings(channel_dir: Path) -> dict:
    path = channel_dir / "settings.yaml"
    if not path.exists():
        raise SettingsError(f"Не найден файл настроек: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        raise SettingsError(f"Не удалось прочитать {path}: {err}") from err
    if not isinstance(data, dict) or not data.get("segments"):
        raise SettingsError(f"В {path} нет раздела segments")
    return data
