"""Общее правило: в конце каждого шага и каждой сессии агент даёт новичку короткую сводку в чате."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
FLOWS = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")
L1 = (ROOT / "docs/spec/01-functional-requirements.md").read_text(encoding="utf-8")

LABELS = ["Что сделано", "Что нашли", "Что решить вам", "Где файлы", "Следующий шаг"]


def _rule():
    m = re.search(r"^## Сводка в конце каждого шага и каждой сессии\n(.*?)(?=^## |^# |\Z)", AGENTS,
                  re.DOTALL | re.MULTILINE)
    assert m, "в AGENTS.md нет раздела «Сводка в конце каждого шага и каждой сессии»"
    return m.group(1)


def test_rule_is_a_general_section_of_agent_part_a():
    assert AGENTS.index("# A. Для агента-продюсера") < AGENTS.index("## Сводка в конце каждого шага и каждой сессии")
    assert AGENTS.index("## Сводка в конце каждого шага и каждой сессии") < AGENTS.index("# B. Для разработки репозитория")


def test_rule_covers_every_step_and_every_session_in_plain_words():
    r = _rule()
    for word in ("каждого шага", "каждой сессии", "простыми словами", "в чате"):
        assert word in r or word in "Сводка в конце каждого шага и каждой сессии", word
    for step in ("сбор", "залёты", "разбор", "ниша", "стратегия", "брифы", "история"):
        assert step in r.lower(), step
    # сессия может оборваться: пауза, ошибка, лимит
    assert "лимит" in r and "пауз" in r and "ошибк" in r


def test_rule_lists_the_five_points_in_order_with_what_each_means():
    r = _rule()
    pos = [r.find(f"**{label}**") for label in LABELS]
    assert all(p >= 0 for p in pos), dict(zip(LABELS, pos))
    assert pos == sorted(pos), pos
    assert "2–4 главные цифры" in r and "не выдумывать" in r
    assert "«да»" in r and "Решать ничего не нужно" in r
    assert "data/<канал>/runs/<месяц>_<сегмент>_v<N>/" in r
    assert "продолжи месяц" in r


def test_rule_keeps_step_outputs_pauses_and_privacy():
    r = _rule()
    assert "остаётся" in r and "последней" in r  # сводка не заменяет то, что шаг уже показал
    assert "паузы" in r  # и не отменяет ожидание слова человека
    assert "ключ" in r and "комментариев" in r  # в сводку не попадают ключ и тексты комментариев целиком


def test_rule_is_not_duplicated_in_claude_md():
    assert "Сводка в конце" not in CLAUDE


def test_month_playbook_points_to_the_rule():
    month = (ROOT / "playbooks/00-month.md").read_text(encoding="utf-8")
    assert "сводк" in month.lower() and "AGENTS.md" in month


def test_spec_has_the_summary_screen_and_the_feature_line():
    row = next(l for l in FLOWS.splitlines() if l.startswith("| Сводка шага |"))
    for label in LABELS:
        assert label in row, label
    assert "«продолжи месяц»" in row
    assert "в конце каждого шага и каждой сессии" in L1
