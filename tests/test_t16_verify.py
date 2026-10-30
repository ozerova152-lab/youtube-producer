"""T16, независимая проверка: подсказка про Claude Cowork в README против критериев приёмки и AGENTS.md (T21)."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
CLAUDE = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
m = re.search(r"^- \*\*Claude Cowork[^\n]*", README, re.MULTILINE)
assert m
SEC = m.group(0)  # подсказка про Cowork: один пункт списка в «Подсказки по агентам»
INSTALL = re.search(r"^## Установка и запуск\n(.*?)(?=^## |\Z)", README, re.DOTALL | re.MULTILINE).group(1)
SECURITY = re.search(r"^## Безопасность\n(.*?)(?=^## |\Z)", README, re.DOTALL | re.MULTILINE).group(1)


def test_cowork_hint_single_and_marked():
    assert len(re.findall(r"^- \*\*Claude Cowork", README, re.MULTILINE)) == 1
    assert SEC.startswith("- **Claude Cowork.**")


def test_steps_in_order():
    # путь целиком: скачать, открыть папку, сказать фразу; ключ и импорт дальше по README
    order = ["Download ZIP", "Откройте папку", "Прочитай AGENTS.md и запусти месяц"]
    pos = [INSTALL.find(x) for x in order]
    assert all(p >= 0 for p in pos), pos
    assert pos == sorted(pos)
    assert README.find(".env.example") > 0 and README.find("docs/import-format.md") > 0


def test_no_unmarked_claims_about_cowork():
    # утвердительный глагол про Cowork без оговорки в том же предложении
    claim = re.compile(
        r"Cowork\s+(умеет|запускает|читает|поддерживает|может|имеет|работает|сам)", re.IGNORECASE
    )
    hedge = re.compile(r"не проверен|не обещаем|смотрите|проверьте|ли\b|не проверял", re.IGNORECASE)
    for sent in re.split(r"(?<=[.;:\n])", SEC):
        if claim.search(sent):
            assert hedge.search(sent), f"утверждение без оговорки: {sent!r}"


def test_no_invented_ui_names():
    for bad in [
        "кнопк",
        "вкладк",
        "меню Cowork",
        "Open Folder",
        "Add folder",
        "Cowork Desktop",
        "Cowork Pro",
    ]:
        assert bad.lower() not in SEC.lower(), bad


def test_cowork_not_claimed_as_checked():
    # в самой подсказке про Cowork статуса нет; статус одной строкой под подсказками: Cowork не проверяли
    assert not re.search(r"проверен|проверено|не проверя", SEC, re.IGNORECASE)
    assert "Основной путь — Claude Code, проверен полностью." in README
    assert "Cowork мы не проверяли: используйте тот же `AGENTS.md` и пишите в [Issues]" in README


def test_consistent_with_claude_md_section_a():
    assert "Ничего не публиковать" in CLAUDE and "ничего не публикует" in SECURITY
    assert (
        re.search(r"`--confirm`.*только после слова человека", CLAUDE)
        and "только после вашего слова" in SECURITY
    )
    assert "«утверждена»" in CLAUDE and "утверждаете вы" in SECURITY and "strategy.md" in SECURITY
    assert "Не читать `.env`" in CLAUDE
    assert "Read(./.env)" in (ROOT / ".claude/settings.json").read_text()


def test_agent_never_told_to_paste_key():
    assert not re.search(
        r"(вставьте|напишите|отправьте)[^.\n]*ключ[^.\n]*(в чат|агенту)", SEC, re.IGNORECASE
    )


def test_readme_size_and_no_secrets():
    assert len(README.splitlines()) < 260  # T21: README стал длиннее (быстрый старт, ошибки, глоссарий)
    assert not re.search(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}", README)


def test_links_alive():
    for rel in re.findall(r"\]\((?!https?:|#)([^)\s]+)\)", README):
        assert (ROOT / rel).exists(), rel

