"""docs/how-it-works.md (T30: вынесено из README): раздел «Как проект помнит прошлые месяцы» — простыми словами, со схемой папок, до 14 строк."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "docs/how-it-works.md").read_text(encoding="utf-8")


def _section():
    m = re.search(r"^## Как проект помнит прошлые месяцы\n(.*?)(?=^## )", README, re.DOTALL | re.MULTILINE)
    assert m, "нет раздела «Как проект помнит прошлые месяцы» в docs/how-it-works.md"
    return m.group(1)


def test_section_is_short_and_placed_after_how_it_works():
    s = _section()
    assert len([line for line in s.strip().splitlines() if line.strip()]) <= 14
    assert README.index("## Как это работает") < README.index("## Как проект помнит прошлые месяцы") \
        < README.index("## Что внутри")


def test_section_shows_folder_scheme_without_personal_data():
    s = _section()
    assert "data/мой-канал/runs/" in s and "2026-09_ru_v1" in s and "2026-10_ru_v1" in s
    assert not re.search(r"/home/|matebook|C:\\Users", s)


def test_section_explains_what_is_read_and_the_statuses():
    s = _section()
    assert "агент ничего в старых папках не меняет" in s
    assert "только прошлые запуски того же сегмента" in s and "`ru` и `en` не смешиваются" in s
    for status in ("«отклонён»", "«позже»", "«принят»"):
        assert status in s, status
    assert "`- Статус:`" in s and "сами" in s  # вернуть отклонённую тему может только человек


def test_user_flow_spec_mentions_the_section():
    flows = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")
    assert "Как проект помнит прошлые месяцы" in flows
