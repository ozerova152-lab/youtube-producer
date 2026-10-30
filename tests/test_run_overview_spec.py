"""Спека описывает обзор запуска `00-overview.md` (T23): тесты на текст спеки, кода пока нет."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPEC = {n: (ROOT / "docs/spec" / f).read_text(encoding="utf-8") for n, f in {
    1: "01-functional-requirements.md", 2: "02-tech-architecture.md",
    3: "03-dev-architecture.md", 4: "04-user-flows.md"}.items()}
ORDER = ["Залётные ролики", "Разбор", "Ниша", "Конкуренты", "Стратегия", "Брифы и сценарии", "План"]


def test_every_layer_names_the_file_the_dates_or_the_command():
    assert "`00-overview.md`" in SPEC[1] and "дата последнего сбора данных" in SPEC[1]
    assert "`00-overview.md`" in SPEC[2] and "`started_on`" in SPEC[2] and "`collected_on`" in SPEC[2]
    assert "`overview`" in SPEC[3] and "`00-overview.md`" in SPEC[3]
    assert "`00-overview.md`" in SPEC[4]


def test_layer_1_row_lists_the_seven_points_in_work_order_and_keeps_old_names():
    row = next(l for l in SPEC[1].splitlines() if l.startswith("| Обзор запуска |"))
    seq = "залётные ролики, разбор, ниша, конкуренты, стратегия, брифы и сценарии, план"
    assert seq in row
    assert "имена остальных файлов запуска не меняются" in row
    assert "«дата неизвестна»" in row


def test_flow_screen_has_seven_numbered_points_in_order_and_states():
    row = next(l for l in SPEC[4].splitlines() if l.startswith("| Обзор запуска |"))
    pos = [row.find(f"{n}. {title}") for n, title in enumerate(ORDER, 1)]
    assert all(p >= 0 for p in pos), pos
    assert pos == sorted(pos)
    for needle in ("⏳ ещё не сделано", "⏭ пропущено: залётов нет", "дата неизвестна", "не правьте его",
                   "`briefs/`", "`plan.md`", "`candidates.md`"):
        assert needle in row, needle
    assert "не попадают ключ, тексты комментариев и названия видео" in row


def test_spec_does_not_promise_renaming_or_a_date_in_the_folder_name():
    assert "01-залёты" not in "".join(SPEC.values())
    for text in SPEC.values():
        assert not re.search(r"\d{4}-\d{2}-\d{2}_ru_v", text)  # дата в имени папки отложена
