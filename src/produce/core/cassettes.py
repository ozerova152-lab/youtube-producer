"""Проверка возраста кассет (записанных ответов YouTube).

Ответы YouTube со временем меняются, поэтому у каждой кассеты в `manifest.json` стоит
дата записи; запись старше шести месяцев `make check` помечает предупреждением.
Предупреждение не роняет проверку: устаревшая кассета ещё работает, её пора обновить.
"""

import json
import sys
from datetime import date
from pathlib import Path

MAX_AGE_DAYS = 183  # около шести месяцев


def stale_cassettes(directory: Path, today: date | None = None) -> list[str]:
    """Тексты предупреждений: кассеты старше 6 месяцев или без даты записи."""
    today = today or date.today()
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    warnings = []
    for cassette in sorted(directory.glob("*.yaml")):
        entry = manifest.get(cassette.name)
        try:
            recorded = date.fromisoformat(entry["recorded_at"])
        except (TypeError, KeyError, ValueError):
            warnings.append(f"Кассета {cassette.name}: нет даты записи в manifest.json")
            continue
        age = (today - recorded).days
        if age > MAX_AGE_DAYS:
            warnings.append(
                f"Кассета {cassette.name} записана {recorded.isoformat()} — "
                f"{age} дн. назад, больше 6 месяцев. Запишите ответы заново"
            )
    return warnings


def main(argv: list[str]) -> int:
    directory = Path(argv[1]) if len(argv) > 1 else Path("examples/demo/cassettes")
    found = stale_cassettes(directory)
    for text in found:
        print(f"ПРЕДУПРЕЖДЕНИЕ: устаревшие записи. {text}")
    if not found:
        print("Кассеты свежие (записаны меньше 6 месяцев назад)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
