"""Общее правило «Как агент отчитывается после каждого шага»: простыми словами, тоном продюсера, шесть частей."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
FLOWS = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")
L1 = (ROOT / "docs/spec/01-functional-requirements.md").read_text(encoding="utf-8")
TITLE = "Как агент отчитывается после каждого шага"

LABELS = ["Что я сделал и зачем", "Что нашёл", "Мои выводы и рекомендация", "Где лежат файлы",
          "Что нужно решить вам", "Следующий шаг"]


def _rule():
    m = re.search(rf"^## {TITLE}\n(.*?)(?=^## |^# |\Z)", AGENTS, re.DOTALL | re.MULTILINE)
    assert m, f"в AGENTS.md нет раздела «{TITLE}»"
    return m.group(1)


def test_old_summary_section_is_replaced_not_duplicated():
    assert "Сводка в конце каждого шага" not in AGENTS
    assert AGENTS.count(f"## {TITLE}") == 1


def test_rule_is_a_general_section_of_agent_part_a():
    pos = AGENTS.index(f"## {TITLE}")
    assert AGENTS.index("# A. Для агента-продюсера") < pos < AGENTS.index("# B. Для разработки репозитория")


def test_rule_covers_every_step_and_names_the_tone():
    r = _rule()
    for step in ("сбор", "залёты", "разбор", "ниша", "стратегия", "брифы", "история"):
        assert step in r.lower(), step
    assert "простыми словами" in r and "тоном продюсера" in r and "клиенту" in r
    assert "короткие абзацы" in r.lower() and "подзаголовк" in r
    assert "сухие списки цифр" in r


def test_rule_lists_six_parts_in_order():
    r = _rule()
    pos = [r.find(f"**{label}") for label in LABELS]  # заголовок может быть длиннее («… и зачем они»)
    assert all(p >= 0 for p in pos), dict(zip(LABELS, pos))
    assert pos == sorted(pos), pos


def test_each_finding_explains_why_it_matters_and_what_it_means_for_the_channel():
    r = _rule()
    assert "«почему это важно»" in r and "«что это значит для вашего канала»" in r
    assert "а не просто цифра" in r
    assert "что бы я сделал" in r and "почему" in r
    assert "что это даёт каналу" in r


def test_files_part_explains_the_archive_and_that_opening_is_optional():
    r = _rule()
    assert "data/<канал>/runs/<месяц>_<сегмент>_v<N>/" in r
    assert "подробный архив" in r and "необязательно" in r


def test_decision_part_is_optional_and_next_step_says_what_it_gives():
    r = _rule()
    assert "только если нужно" in r and "«да»" in r and "«утверждена»" in r
    assert "что он даст" in r and "продолжи месяц" in r


def test_terms_are_explained_at_first_mention():
    r = _rule()
    for term in ("залёт", "ДРР", "квота", "воронка"):
        assert term in r, term
    assert "при первом упоминании" in r


def test_rule_keeps_numbers_honest_pauses_interrupted_sessions_and_privacy():
    r = _rule()
    assert "только из файлов запуска" in r and "не выдумывать" in r
    assert "последним" in r and "остаётся" in r
    assert "паузы" in r
    assert "оборвалась" in r and "лимит" in r
    assert "ключ" in r and "комментариев" in r


def test_rule_is_not_duplicated_in_claude_md():
    assert TITLE not in CLAUDE


def test_month_playbook_points_to_the_rule():
    month = (ROOT / "playbooks/00-month.md").read_text(encoding="utf-8")
    assert TITLE in month and "AGENTS.md" in month


def test_spec_has_the_report_screen_and_the_feature_line():
    row = next(l for l in FLOWS.splitlines() if l.startswith("| Отчёт после шага |"))
    for label in LABELS:
        assert label in row, label
    assert "«продолжи месяц»" in row and "необязательно" in row
    assert "после каждого шага он отчитывается перед новичком" in L1
    assert "Сводка шага" not in FLOWS
