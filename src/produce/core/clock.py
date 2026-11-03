"""Текущее время проекта в одном месте.

`PRODUCE_NOW` (ГГГГ-ММ-ДД) нужен автотестам: записанные ответы не стареют вместе с календарём.
Даты запусков берутся только отсюда, а не из `date.today()`.
"""

import os
from datetime import UTC, datetime


def now() -> datetime:
    fixed = os.environ.get("PRODUCE_NOW", "").strip()
    if fixed:
        return datetime.fromisoformat(fixed).replace(tzinfo=UTC)
    return datetime.now(UTC)
