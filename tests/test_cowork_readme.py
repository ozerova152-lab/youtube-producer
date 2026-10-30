"""T16/T21: README, подсказка про Claude Cowork в разделе «Подсказки по агентам»: честные пометки и живые ссылки."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _block(text, start, stop):
    m = re.search(rf"^{re.escape(start)}[^\n]*\n(.*?)(?={stop}|\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, f"нет блока {start}"
    return m.group(1)


AGENTS_HINTS = _block(README, "### Подсказки по агентам", r"^### |^## ")
# подсказка про Cowork — один пункт списка: от «- **Claude Cowork» до следующего пункта или абзаца
COWORK = re.search(r"^- \*\*Claude Cowork[^\n]*", AGENTS_HINTS, re.MULTILINE).group(0)
INSTALL = _block(README, "## Установка и запуск", r"^## ")


def test_cowork_hint_is_short_and_marked_unchecked():
    assert COWORK.startswith("- **Claude Cowork — не проверено.**")
    assert len(COWORK) < 900  # коротка подсказка, а не отдельная инструкция


def test_exact_agent_phrase_in_install_section():
    assert "«Прочитай AGENTS.md и запусти месяц»" in INSTALL
    assert "«Прочитай AGENTS.md и продолжи месяц»" in INSTALL


def test_unchecked_points_named():
    assert "запуск именно в Cowork" in COWORK
    assert "запускать команды скрипта" in COWORK
    assert "`AGENTS.md`" in COWORK and "читает ли он" in COWORK
    assert "Настоящий сбор по ключу проверен в Claude Code, в Cowork не проверен" in COWORK


def test_checked_agent_is_claude_code_only():
    assert "- **Claude Code — проверен.**" in AGENTS_HINTS
    assert "демо-данных" in AGENTS_HINTS and "записанных ответах YouTube" in AGENTS_HINTS


def test_key_paragraph():
    assert "не вставляйте ключ в чат" in AGENTS_HINTS
    assert "только в Claude Code" in AGENTS_HINTS
    assert "лишь на инструкции в `AGENTS.md`" in AGENTS_HINTS


def test_pauses_and_bans_repeated():
    security = _block(README, "## Безопасность", r"^## ")
    assert "ничего не публикует" in security
    assert "`--confirm`" in security and "только после вашего слова" in security
    assert "стратегию утверждаете вы" in security


def test_links_alive_and_no_keys():
    for rel in re.findall(r"\]\((?!https?:|#)([^)\s]+)\)", README):
        assert (ROOT / rel).exists(), rel
    assert (ROOT / ".env.example").is_file()
    assert not re.search(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}", README)
    assert "YOUTUBE_API_KEY=" not in AGENTS_HINTS
