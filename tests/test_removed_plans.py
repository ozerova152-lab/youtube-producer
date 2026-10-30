"""Планы про «VK Видео» и «превращение брифов в промпты для нейровидео» убраны отовсюду (решение человека, 2026-10-30)."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
PHRASES = re.compile(r"VK ?Видео|VK Video|нейровидео", re.IGNORECASE)


def _scanned():
    files = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CLAUDE.md"]
    files += sorted((ROOT / "site").glob("*.html"))
    for folder in ("docs/spec", "docs/dev", "playbooks", "templates"):
        files += sorted((ROOT / folder).rglob("*.md"))
    files += sorted(p for p in (ROOT / "docs/tasks").glob("*.md"))
    return [p for p in files if p.is_file()]


def test_removed_plans_do_not_appear_anywhere_in_user_facing_docs():
    hits = [f"{p.relative_to(ROOT)}:{n}" for p in _scanned()
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if PHRASES.search(line)]
    assert hits == [], hits


def test_brief_structure_rationale_is_neutral_and_present():
    playbook = (ROOT / "playbooks/06-briefs-plan.md").read_text(encoding="utf-8")
    assert "структура единая" in playbook
    assert "бриф любого вида читается и проверяется одинаково" in playbook
    task = (ROOT / "docs/tasks/T11-playbook-briefs-long.md").read_text(encoding="utf-8")
    assert "бриф любого вида читался и проверялся одинаково" in task


def test_spec_not_doing_table_keeps_the_other_rows():
    l1 = (ROOT / "docs/spec/01-functional-requirements.md").read_text(encoding="utf-8")
    table = l1.split("## Что НЕ делаем")[1].split("\n## ")[0]
    for row in ("Публикация, загрузка видео", "Парсинг сайта YouTube", "Закрытая аналитика канала"):
        assert row in table, row
    flows = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")
    assert "| Работа с закрытой аналитикой канала | Следующие версии (слой 1) |" in flows
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "**Windows** только через WSL." in readme and "**Ещё нет:**" not in readme
