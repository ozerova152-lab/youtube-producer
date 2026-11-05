"""T29, независимая проверка: витрина без форм «не провер…», статус одинаков в README, числа совпадают."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
HTML = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
RU = (ROOT / "README.md").read_text(encoding="utf-8")
EN = (ROOT / "README.en.md").read_text(encoding="utf-8")
SPEC = (ROOT / "docs" / "spec" / "04-user-flows.md").read_text(encoding="utf-8")
STATUS = (
    "Полностью проверен в Claude Code и Codex. Рассчитан и на другие агенты: те же инструкции работают "
    "без скрипта сбора данных, данные можно вставить в чат. Расскажите, как получилось"
)
ISSUES = "https://github.com/ozerova152-lab/youtube-producer/issues"


def test_showcase_has_no_negative_check_forms_anywhere():
    # любые формы: не проверен/непроверен/не проверялся/не проверяли/не тестировали, в т.ч. в атрибутах и комментариях
    assert not re.search(r"не\s*провер|не\s*тестир|not\s+tested|untested", HTML, re.IGNORECASE)


def test_showcase_status_verbatim_with_issues_link_and_in_spec():
    assert f'<a href="{ISSUES}">Расскажите, как получилось</a>' in HTML
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", HTML))
    # T34: пометок о проверке на витрине нет, остаётся только ссылка «Расскажите, как получилось»
    for gone in ("Полностью проверен", "Рассчитан и на другие агенты", "проверен в Claude Code"):
        assert gone not in plain and gone not in SPEC, gone
    assert "Расскажите, как получилось" in plain and "Расскажите, как получилось" in SPEC


def test_showcase_follows_ui_rules():
    assert "cdn" not in HTML.lower() and "vendor/pico.min.css" in HTML
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", HTML)
    assert len(re.findall(r"<script", HTML)) == 1


def test_readmes_same_numbers_and_commands():
    # T30: в README остались быстрый старт, ключ и демо; статус, обложки и режим чата живут в docs (русские, T31 переведёт)
    for token in ("30", "10,000", "make setup", "make add-key", "make reset", "00-overview.md", "thumbs/"):
        assert token in EN, token
    for token in ("make setup", "make add-key", "make reset", "00-overview.md"):
        assert token in RU, token
    docs = "".join((ROOT / "docs" / n).read_text(encoding="utf-8") for n in ("compatibility.md", "chat-mode.md", "dev/agent-status.md"))
    for token in ("30.10.2026", "playbooks/no-terminal.md", "thumbs/"):
        assert token in docs, token
    assert re.search(r"5[–-]20", docs) and re.search(r"\b60\b", docs)


def test_readmes_do_not_overstate_and_do_not_leak():
    compat = (ROOT / "docs/dev/agent-status.md").read_text(encoding="utf-8")  # T34: статус только здесь
    for text in (RU, EN, compat):
        assert not re.search(r"/home/|matebook|AIza", text)
        assert not re.search(r"Cowork[^.]{0,40}(fully|полностью) (tested|проверен)", text)
    # T34: статус по агентам стоит один раз, в заметке для разработчика; README и витрина на неё не ссылаются
    assert "Cowork мы не проверяли" in compat and "на реальном канале мы тоже не проверяли" in compat
    assert "agent-status" not in RU and "agent-status" not in EN and "agent-status" not in HTML
