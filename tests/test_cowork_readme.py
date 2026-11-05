"""T16/T21/T30: подсказка про Cowork и статус по агентам лежат один раз в docs/compatibility.md: честные пометки и живые ссылки.

T30 вынес подсказки, статус и ограничения из README в docs: проверки те же, меняется только файл, который читается;
в самом README слов «проверен…» быть не должно (статус живёт в одном месте).
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
COMPAT = (ROOT / "docs/compatibility.md").read_text(encoding="utf-8")
LIMITS_DOC = (ROOT / "docs/limits-and-security.md").read_text(encoding="utf-8")
DEVNOTE = (ROOT / "docs/dev/agent-status.md").read_text(encoding="utf-8")  # T34: статус проверки только здесь


def _block(text, start, stop):
    m = re.search(rf"^{re.escape(start)}[^\n]*\n(.*?)(?={stop}|\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, f"нет блока {start}"
    return m.group(1)


AGENTS_HINTS = _block(COMPAT, "## Подсказки по агентам", r"^## ")
# подсказка про Cowork — один пункт списка: от «- **Claude Cowork» до следующего пункта или абзаца
COWORK = re.search(r"^- \*\*Claude Cowork[^\n]*", AGENTS_HINTS, re.MULTILINE).group(0)
QUICK_START = _block(README, "## Быстрый старт", r"^## ")


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


def test_exact_agent_phrase_in_quick_start():
    assert "«Прочитай AGENTS.md и запусти месяц»" in QUICK_START
    assert "«Прочитай AGENTS.md и продолжи месяц»" in QUICK_START


# Единственное разрешённое утверждение «проверено» про другой агент (слова человека, 2026-10-30).
CODEX_FACT = "Codex проверен на реальном канале (30.10.2026) от установки до брифов"
CODEX_STEPS = "установка, ключ, сбор данных, залёты, ниша и кандидаты, стратегия, брифы"
CLAUDE_FACT = "Основной путь — Claude Code, проверен полностью"
STATUS = (f"**{CLAUDE_FACT}.** {CODEX_FACT}: {CODEX_STEPS}. Cowork мы не проверяли: используйте тот же `AGENTS.md` "
          "и пишите в [Issues](https://github.com/ozerova152-lab/youtube-producer/issues).")


def _without_allowed(text):
    """Убирает ровно две разрешённые формулировки «проверен»: Claude Code и Codex (дословно)."""
    return text.replace(CLAUDE_FACT, "").replace(CODEX_FACT, "")


def test_status_is_stated_once_in_developer_note_only():
    # T34: пометки о проверке лежат только в заметке для разработчика, не в docs/compatibility.md
    assert STATUS in DEVNOTE
    assert DEVNOTE.count(CODEX_FACT) == 1 and DEVNOTE.count(CLAUDE_FACT) == 1
    assert DEVNOTE.count(CODEX_STEPS) == 1
    assert DEVNOTE.count("Cowork мы не проверяли") == 1
    assert "Обычный чат без терминала" in DEVNOTE and "мы тоже не проверяли" in DEVNOTE
    assert "Для всех используется тот же `AGENTS.md`" in COMPAT
    assert CODEX_FACT not in COMPAT and CLAUDE_FACT not in COMPAT and "Cowork мы не проверяли" not in COMPAT


def test_no_claims_about_agents_beyond_the_allowed_sentences():
    # статус живёт только в docs/compatibility.md: в README, ограничениях и проверка-тексте его нет
    for name, text in (("README.md", README), ("limits-and-security.md", LIMITS_DOC)):
        assert CODEX_FACT not in text and CLAUDE_FACT not in text, name
        assert not re.search(r"проверен", text), name
    rest = _without_allowed(DEVNOTE)
    # про Cowork ничего «проверенного», про Codex ничего сверх точной фразы выше
    assert not re.search(r"(Cowork|Codex)[^.\n]{0,40}проверен", rest)
    assert not re.search(r"Claude Code[^.\n]{0,40}проверен", rest)
    assert not re.search(r"не сверяли|лишь на базовом|проверен лишь|проверен полностью", rest)
    assert not re.search(r"Codex[^.\n]{0,40}не проверя", DEVNOTE)


def test_readme_links_to_status_instead_of_repeating_it():
    assert "docs/compatibility.md" in README and "docs/limits-and-security.md" in README


def test_key_paragraph():
    assert "не вставляйте ключ в чат" in COMPAT
    assert "только в Claude Code" in COMPAT
    assert "лишь на инструкции в `AGENTS.md`" in COMPAT
    assert "YOUTUBE_API_KEY=" not in COMPAT


def test_pauses_and_bans_repeated():
    security = _block(LIMITS_DOC, "## Безопасность", r"^## ")
    assert "ничего не публикует" in security
    assert "`--confirm`" in security and "только после вашего слова" in security
    assert "стратегию утверждаете вы" in security


def test_limits_keep_all_bullets():
    limits = _block(LIMITS_DOC, "## Для чего проект не подходит и ограничения", r"^## ")
    for word in ("Не публикует", "Только публичные числа", "Только официальный API", "Не работает сам по себе",
                 "Квота ограничена", "Windows"):
        assert word in limits, word


def test_links_alive_and_no_keys():
    for doc, base in [(README, ROOT), *[((ROOT / "docs" / n).read_text(encoding="utf-8"), ROOT / "docs")
                                         for n in ("compatibility.md", "limits-and-security.md", "how-it-works.md",
                                                   "chat-mode.md", "glossary.md", "windows-wsl.md")]]:
        for rel in re.findall(r"\]\((?!https?:|#)([^)\s]+)\)", doc):
            path = rel.split("#")[0]
            if path:
                assert (base / path).exists(), rel
        assert not re.search(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}", doc)
    assert (ROOT / ".env.example").is_file()
