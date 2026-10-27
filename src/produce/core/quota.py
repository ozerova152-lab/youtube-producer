"""Дневной учёт квоты YouTube.

Квота общая на ключ и сутки, поэтому учёт лежит одним файлом рядом с папками каналов
(`data/quota.json`), а не в `run.json` отдельного запуска.
"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from produce.core.files import read_json, write_json_atomic

DAILY_LIMIT = 10_000
# YouTube обнуляет квоту в полночь по тихоокеанскому времени.
_QUOTA_TZ = ZoneInfo("America/Los_Angeles")


def quota_day(now: datetime | None = None) -> date:
    return (now or datetime.now(_QUOTA_TZ)).astimezone(_QUOTA_TZ).date()


def ledger_path(channel_dir: Path) -> Path:
    return channel_dir.parent / "quota.json"


def spent_today(ledger: Path, day: date | None = None) -> int:
    day = day or quota_day()
    if not ledger.exists():
        return 0
    data = read_json(ledger)
    return int(data.get(day.isoformat(), 0)) if isinstance(data, dict) else 0


def remaining_today(ledger: Path, day: date | None = None) -> int:
    return max(DAILY_LIMIT - spent_today(ledger, day), 0)


def add_spent(ledger: Path, units: int, day: date | None = None) -> int:
    """Прибавляет расход к сумме за сутки по всем запускам; возвращает новую сумму."""
    day = day or quota_day()
    data = read_json(ledger) if ledger.exists() else {}
    if not isinstance(data, dict):
        data = {}
    # Старые сутки не нужны: оставляем только текущие, чтобы файл не рос.
    data = {k: v for k, v in data.items() if k >= day.isoformat()}
    data[day.isoformat()] = int(data.get(day.isoformat(), 0)) + units
    write_json_atomic(ledger, data)
    return data[day.isoformat()]


def mark_exhausted(ledger: Path, day: date | None = None) -> None:
    """YouTube сказал «квота закончилась»: до завтра считаем сутки потраченными."""
    day = day or quota_day()
    left = remaining_today(ledger, day)
    if left:
        add_spent(ledger, left, day)
