"""T34: на витрине и в README нет пометок «проверено / не проверено»; статус лежит только в заметке для разработчика."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RU = (ROOT / "README.md").read_text(encoding="utf-8")
EN = (ROOT / "README.en.md").read_text(encoding="utf-8")
HTML = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
COMPAT = (ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8")
NOTE = (ROOT / "docs" / "dev" / "agent-status.md").read_text(encoding="utf-8")
ISSUES = "https://github.com/ozerova152-lab/youtube-producer/issues"
BANNED = re.compile(r"проверен|проверя|проверено|tested|Рассчитан и на другие|Основной путь", re.IGNORECASE)


def test_readmes_and_showcase_have_no_verification_notes():
    for name, text in (("README.md", RU), ("README.en.md", EN), ("site/index.html", HTML)):
        found = BANNED.findall(text)
        # слово «проверьте» (глагол-просьба в быстром старте) не пометка; «Проверьте» не совпадает с шаблоном
        assert not found, (name, found)


def test_only_the_issues_link_remains():
    assert f'<a href="{ISSUES}">Расскажите, как получилось</a>' in HTML
    assert f"[Issues]({ISSUES})" in RU and f"[Issues]({ISSUES})" in EN
    assert "Расскажите, как получилось" in RU and "Tell us how it went" in EN


def test_nobody_links_to_the_developer_note():
    for path in [ROOT / "README.md", ROOT / "README.en.md", ROOT / "site" / "index.html", *(ROOT / "docs").glob("*.md"),
                 ROOT / "AGENTS.md", ROOT / "CLAUDE.md"]:
        assert "agent-status" not in path.read_text(encoding="utf-8"), path.name


def test_compatibility_doc_has_no_status_and_note_keeps_it_once():
    assert "## Статус" not in COMPAT and "Основной путь" not in COMPAT and "Cowork мы не проверяли" not in COMPAT
    assert NOTE.count("## Статус") == 1 and NOTE.count("Основной путь — Claude Code, проверен полностью") == 1
    # доки для человека не ссылаются на статус
    for name in ("limits-and-security.md", "chat-mode.md", "how-it-works.md", "glossary.md"):
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert "compatibility.md#статус" not in text and "статус по агентам" not in text.lower(), name


def test_spec_does_not_require_the_removed_phrase():
    spec = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "docs" / "spec").glob("*.md"))
    for gone in ("Полностью проверен в Claude Code и Codex", "Рассчитан и на другие агенты"):
        assert gone not in spec, gone
