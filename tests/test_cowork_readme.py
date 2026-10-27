"""T16: README, раздел «Вариант без Claude Code» (Claude Cowork): честные пометки и живые ссылки."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _section(text, title):
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, f"нет раздела {title}"
    return m.group(1)


SECTION = _section(README, "Вариант без Claude Code")


def _list_after(marker):
    m = re.search(rf"\*\*{marker}:\*\*\n\n((?:- .*\n?)+)", SECTION)
    assert m, f"нет списка {marker}"
    return m.group(1)


def test_section_steps():
    for needle in ["Download ZIP", "Распакуйте", "Claude Cowork", ".env.example", "`.env`",
                   "docs/import-format.md", "импорт"]:
        assert needle in SECTION, needle


def test_exact_agent_phrase():
    assert "«Прочитай CLAUDE.md и запусти месяц»" in SECTION


def test_checked_and_unchecked_lists():
    checked = _list_after("Проверено")
    unchecked = _list_after("Не проверено")
    assert "демо-данных" in checked and "записанных ответах YouTube" in checked
    assert "команды скрипта" in checked and "тесты проекта" in checked
    assert "запуск именно в Claude Cowork" in unchecked
    assert "запускать команды скрипта" in unchecked
    assert "`CLAUDE.md`" in unchecked
    assert "настоящий сбор по ключу" in unchecked


def test_key_paragraph():
    assert "не вставляйте его в чат" in SECTION
    assert "только в Claude Code" in SECTION
    assert "лишь на инструкции в `CLAUDE.md`" in SECTION
    assert "проверьте сами" in SECTION


def test_pauses_and_bans_repeated():
    assert "ничего не публикует" in SECTION
    assert "`--confirm`" in SECTION and "только после вашего слова" in SECTION
    assert "стратегию утверждаете вы" in SECTION


def test_links_alive_and_no_keys():
    for rel in re.findall(r"\]\((?!https?:|#)([^)\s]+)\)", SECTION):
        assert (ROOT / rel).exists(), rel
    assert (ROOT / ".env.example").is_file()
    assert not re.search(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}", README)
    assert "YOUTUBE_API_KEY=" not in SECTION
