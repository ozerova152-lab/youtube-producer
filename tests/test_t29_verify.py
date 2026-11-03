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
    plain = re.sub(r"<[^>]+>", "", HTML)
    assert STATUS in re.sub(r"\s+", " ", plain)
    assert STATUS in SPEC


def test_showcase_follows_ui_rules():
    assert "cdn" not in HTML.lower() and "vendor/pico.min.css" in HTML
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", HTML)
    assert len(re.findall(r"<script", HTML)) == 1


def test_readmes_same_numbers_and_commands():
    for token in (
        "30",
        "60",
        "5-20",
        "10,000",
        "make setup",
        "make add-key",
        "make reset",
        "00-overview.md",
        "thumbs/",
        "playbooks/no-terminal.md",
        "30 Oct 2026",
    ):
        assert token in EN, token
    for token in (
        "30.10.2026",
        "playbooks/no-terminal.md",
        "make add-key",
        "make reset",
        "thumbs/",
    ):
        assert token in RU, token
    assert re.search(r"5[–-]20", RU) and re.search(r"\b60\b", RU)


def test_readmes_do_not_overstate_and_do_not_leak():
    for text in (RU, EN):
        assert not re.search(r"/home/|matebook|AIza", text)
        assert not re.search(r"Cowork[^.]{0,40}(fully|полностью) (tested|проверен)", text)
    assert "We did not test Cowork" in EN and "Cowork мы не проверяли" in RU
    assert (
        "has also not been tested on a real channel" in EN
        and "на реальном канале мы тоже не проверяли" in RU
    )
