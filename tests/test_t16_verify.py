"""T16, независимая проверка: раздел README «Вариант без Claude Code» против критериев приёмки и CLAUDE.md."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
m = re.search(r"^## Вариант без Claude Code\n(.*?)(?=^## |\Z)", README, re.DOTALL | re.MULTILINE)
assert m
SEC = m.group(1)


def test_section_between_codex_and_inside_and_single():
    assert README.count("## Вариант без Claude Code") == 1


def test_steps_in_order():
    order = [
        "Download ZIP",
        "Распакуйте",
        "Откройте распакованную папку в Claude Cowork",
        "Прочитай CLAUDE.md и запусти месяц",
        ".env.example",
        "docs/import-format.md",
    ]
    pos = [SEC.find(s) for s in order]
    assert all(p >= 0 for p in pos), pos
    assert pos == sorted(pos)


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


def test_unchecked_is_not_in_checked():
    checked = SEC.split("**Проверено:**")[1].split("**Не проверено:**")[0]
    assert "Cowork" not in checked


def test_consistent_with_claude_md_section_a():
    assert "Ничего не публиковать" in CLAUDE and "ничего не публикует" in SEC
    assert (
        re.search(r"`--confirm`.*только после слова человека", CLAUDE)
        and "только после вашего слова" in SEC
    )
    assert "«утверждена»" in CLAUDE and "утверждаете вы" in SEC and "strategy.md" in SEC
    assert "Не читать `.env`" in CLAUDE
    assert "Read(./.env)" in (ROOT / ".claude/settings.json").read_text()


def test_agent_never_told_to_paste_key():
    assert not re.search(
        r"(вставьте|напишите|отправьте)[^.\n]*ключ[^.\n]*(в чат|агенту)", SEC, re.IGNORECASE
    )


def test_readme_size_and_no_secrets():
    assert len(README.splitlines()) < 120
    assert not re.search(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}", README)


def test_links_alive():
    for rel in re.findall(r"\]\((?!https?:|#)([^)\s]+)\)", README):
        assert (ROOT / rel).exists(), rel

