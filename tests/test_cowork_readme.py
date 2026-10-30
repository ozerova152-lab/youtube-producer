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


NEUTRAL = ("Основной путь — Claude Code. В других агентах (Cowork, Codex) используйте тот же `AGENTS.md`; "
           "если что-то не заработало, напишите в [Issues](https://github.com/ozerova152-lab/youtube-producer/issues).")


def test_neutral_line_under_hints_and_limits_do_not_claim_checks():
    assert NEUTRAL in AGENTS_HINTS
    limits = _block(README, "## Для чего проект не подходит и ограничения", r"^## ")
    assert "Основной путь — Claude Code." in limits
    assert "используется тот же `AGENTS.md`" in limits
    assert not re.search(r"не проверя|не проверен|проверен", limits)


def test_no_checked_or_unchecked_claims_about_agents_anywhere():
    # ни «не проверяли», ни «проверен лишь…», ни «проверен» про агентов в README нет
    assert not re.search(r"не проверя|не проверен|не сверяли|лишь на базовом", README)
    assert not re.search(r"(Cowork|Codex)[^.\n]{0,40}проверен", README)


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
