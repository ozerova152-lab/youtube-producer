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


def test_cowork_hint_is_short_and_makes_no_checked_claim():
    assert COWORK.startswith("- **Claude Cowork.**")
    assert len(COWORK) < 200  # короткая подсказка, а не отдельная инструкция
    # про Cowork не утверждается ни «проверено», ни «работает»
    assert not re.search(r"проверен|проверено|работает|умеет", COWORK, re.IGNORECASE)


def test_three_hints_are_equal_in_length_and_form():
    hints = [l for l in AGENTS_HINTS.splitlines() if l.startswith("- **")]
    assert [h.split("**")[1] for h in hints] == ["Claude Code.", "Claude Cowork.", "Codex."]
    sizes = [len(h) for h in hints]
    assert max(sizes) - min(sizes) < 60, sizes


def test_exact_agent_phrase_in_install_section():
    assert "«Прочитай AGENTS.md и запусти месяц»" in INSTALL
    assert "«Прочитай AGENTS.md и продолжи месяц»" in INSTALL


# Единственное разрешённое утверждение «проверено» про другой агент (слова человека, 2026-10-30).
CODEX_FACT = "Codex проверен на реальном канале (30.10.2026) от установки до брифов"
CODEX_STEPS = "установка, ключ, сбор данных, залёты, ниша и кандидаты, стратегия, брифы"
CLAUDE_FACT = "Основной путь — Claude Code, проверен полностью"
STATUS = (f"**{CLAUDE_FACT}.** {CODEX_FACT}: {CODEX_STEPS}. Cowork мы не проверяли: используйте тот же `AGENTS.md` "
          "и пишите в [Issues](https://github.com/ozerova152-lab/youtube-producer/issues).")


def _without_allowed(text):
    """Убирает ровно три разрешённые формулировки «проверен»: Claude Code и Codex (дословно)."""
    return text.replace(CLAUDE_FACT, "").replace(CODEX_FACT, "")


def test_status_line_under_hints_and_limits_say_exactly_what_was_checked():
    assert STATUS in AGENTS_HINTS
    limits = _block(README, "## Для чего проект не подходит и ограничения", r"^## ")
    assert CLAUDE_FACT in limits
    assert CODEX_FACT in limits and "Cowork мы не проверяли" in limits
    assert "используется тот же `AGENTS.md`" in limits
    # кроме двух дословных фраз (Claude Code, Codex), слова «проверен…» в ограничениях быть не должно
    assert not re.search(r"проверен", _without_allowed(limits))


def test_no_claims_about_agents_beyond_the_allowed_sentences():
    assert README.count(CODEX_FACT) == 2  # строка под подсказками и раздел ограничений, больше нигде
    assert README.count(CLAUDE_FACT) == 2
    assert README.count(CODEX_STEPS) == 1  # полный перечень этапов Codex только в строке под подсказками
    rest = _without_allowed(README)
    # про Cowork ничего «проверенного», про Codex ничего сверх точной фразы выше
    assert not re.search(r"(Cowork|Codex)[^.\n]{0,40}проверен", rest)
    assert not re.search(r"Claude Code[^.\n]{0,40}проверен", rest)
    assert not re.search(r"не сверяли|лишь на базовом|проверен лишь|проверен полностью", rest)
    # про Cowork сказано прямо, что не проверяли; про Codex «не проверяли» нет
    assert README.count("Cowork мы не проверяли") == 2
    assert not re.search(r"Codex[^.\n]{0,40}не проверя", README)


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
