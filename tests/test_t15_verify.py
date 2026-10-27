"""Независимая проверка T15 (сценарий месяца, README, ссылки, секреты, витрина).

Написана от критериев приёмки. Числа витрины считаются здесь заново из import.csv.
Сценарий 00-month доказывается структурно: живой сессии агента нет.
"""

import csv
import re
import statistics
import subprocess
from pathlib import Path

import pytest

from produce.core.runs import STAGES

ROOT = Path(__file__).resolve().parent.parent
MONTH = (ROOT / "playbooks/00-month.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
SITE = (ROOT / "site/index.html").read_text(encoding="utf-8")


def _section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}.*?(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, f"нет раздела «{title}»"
    return m.group(0)


# ---- критерии 1-2: сценарий месяца ----

def test_steps_table_goes_01_to_07_in_order():
    refs = re.findall(r"playbooks/(0[1-7])-", _section(MONTH, "Порядок шагов"))
    firsts = []
    for r in refs:
        if r not in firsts:
            firsts.append(r)
    assert firsts == ["01", "02", "03", "04", "05", "06", "07"]


def test_every_stage_has_an_action_row():
    block = _section(MONTH, "Продолжить месяц («продолжи месяц»)")
    rows = [ln for ln in block.splitlines() if ln.startswith("| «")]
    covered = set()
    for row in rows:
        cell = row.split("|")[1]
        covered |= set(re.findall(r"«([^»]+)»", cell))
    assert set(STAGES) <= covered, set(STAGES) - covered
    for row in rows:
        assert re.search(r"playbooks/0\d-|Месяц закончен|Показать паузу|Раздел «Статусы", row), row


def test_pauses_present():
    steps = _section(MONTH, "Порядок шагов")
    assert "Оценка квоты" in steps and "ждать «да»" in steps
    assert "Твёрдая пауза до «утверждена»" in steps
    assert "Пауза на статусы брифов" in steps
    assert "принят / отклонён / позже" in steps
    # слово в чате без правки файла не снимает паузу стратегии
    assert "не разрешение" in MONTH
    assert "Замените его сами" in MONTH


def test_bans_and_data_not_instructions():
    rules = _section(MONTH, "Правила на весь месяц")
    assert "Ничего не публиковать" in rules
    assert "данные, а не инструкции" in rules
    assert "Не читать `.env`" in rules
    assert "`settings.yaml` не менять" in rules
    assert "`--confirm` ставится только после слова человека" in rules
    assert "Не выдумывать" in rules


def test_no_settings_and_agent_limit_branches():
    assert "Ветка «нет настроек»" in MONTH and "Настроек канала нет" in MONTH
    assert "Не найден файл настроек" in MONTH
    lim = _section(MONTH, "Если лимит подписки на агента кончился")
    assert "Лимит агента на сегодня закончился" in lim and "продолжи месяц" in lim
    # тексты берутся из потока (спека)
    flows = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")
    assert "Лимит агента на сегодня закончился" in flows
    assert "Настроек канала нет" in flows


def test_month_playbook_never_instructs_to_set_confirm_itself():
    # --confirm упоминается только в запретительном контексте
    for ln in MONTH.splitlines():
        if "--confirm" in ln:
            assert any(w in ln for w in ("только после слова", "Подтверждение", "Это относится", "не ставился без")), ln


def test_month_playbook_has_no_publish_tools():
    low = MONTH.lower()
    for bad in ("youtube.com/upload", "videos.insert", "опубликуй сам"):
        assert bad not in low


# ---- критерий 3: ссылки ----

def test_claude_md_links_equal_playbook_files():
    linked = set(re.findall(r"playbooks/([0-9]{2}-[\w-]+\.md)", CLAUDE))
    actual = {p.name for p in (ROOT / "playbooks").glob("[0-9][0-9]-*.md")}
    assert linked == actual
    for name in linked:
        assert (ROOT / "playbooks" / name).is_file()


def test_relative_links_in_readme_and_playbooks_alive():
    files = [ROOT / "README.md", *(ROOT / "playbooks").glob("*.md")]
    for f in files:
        txt = f.read_text(encoding="utf-8")
        targets = re.findall(r"\]\((?!https?:|#|mailto:)([^)\s]+)\)", txt)
        targets += re.findall(r"`((?:playbooks|docs|templates|examples|site)/[\w./-]+\.\w+)`", txt)
        for t in targets:
            path = t.split("#")[0]
            if any(ch in path for ch in "<>*"):
                continue
            base = ROOT if (f.name == "README.md" or "/" in path and path.split("/")[0] in
                            {"playbooks", "docs", "templates", "examples", "site"}) else f.parent
            assert (base / path).exists() or (f.parent / path).exists(), f"{f.name}: {t}"


def test_missing_playbook_reference_would_be_detected(tmp_path):
    """Враждебный: детектор ловит ссылку на несуществующий сценарий."""
    fake = CLAUDE + "\n| 8 | `playbooks/99-ghost.md` | x |\n"
    linked = set(re.findall(r"playbooks/([0-9]{2}-[\w-]+\.md)", fake))
    actual = {p.name for p in (ROOT / "playbooks").glob("[0-9][0-9]-*.md")}
    assert linked != actual


# ---- критерий 4: README ----

@pytest.mark.parametrize("needle", [
    "Google Cloud", "YouTube Data API v3", ".env", "cp .env.example .env", "Claude Code",
    "запусти месяц", "оценк", "импорт", "docs/import-format.md", "Codex", "CLAUDE.md",
    "WSL", "make setup", "Без ключа",
])
def test_readme_mentions(needle):
    assert needle.lower() in README.lower(), needle


def test_readme_codex_honest_note_and_no_tutorials():
    codex = _section(README, "В Codex")
    assert "лишь на базовом уровне" in codex
    assert "ссылку на репозиторий" in codex and "CLAUDE.md" in codex
    assert "Отдельной поддержки Codex нет" in codex
    assert len(README.splitlines()) < 120  # не учебник
    assert "```mermaid" not in README and "![" not in README


def test_readme_has_no_realistic_key():
    # реальный формат ключа Google: AIza + 35 символов
    assert not re.search(r"AIza[0-9A-Za-z_\-]{35}", README)
    assert not re.search(r"sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}", README)


def test_key_regex_catches_a_sample():
    sample = "YOUTUBE_API_KEY=AIza" + "A" * 35
    assert re.search(r"AIza[0-9A-Za-z_\-]{35}", sample)


# ---- критерий 6: секреты ----

def _tracked_and_new():
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.split("\0") if p and (ROOT / p).is_file()]


SECRET_RE = re.compile(r"AIza[0-9A-Za-z_\-]{35}|\bsk-[A-Za-z0-9_\-]{20,}|\bghp_[A-Za-z0-9]{30,}"
                       r"|github_pat_[A-Za-z0-9_]{30,}|xox[bp]-[A-Za-z0-9\-]{20,}")


def test_no_secret_patterns_in_repo_files():
    hits = []
    for f in _tracked_and_new():
        if f.suffix in {".png", ".jpg", ".css", ".woff2"} or "vendor" in f.parts:
            continue
        try:
            txt = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SECRET_RE.search(txt):
            hits.append(str(f.relative_to(ROOT)))
    assert hits == []


def test_no_secret_patterns_in_git_history():
    log = subprocess.run(["git", "log", "-p", "--all", "--no-color"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert not SECRET_RE.search(log)


def test_gitleaks_files_and_history_clean():
    for args in (["--no-git"], []):
        res = subprocess.run(["gitleaks", "detect", *args, "--source", ".", "--config",
                              ".gitleaks.toml", "--no-banner"], cwd=ROOT,
                             capture_output=True, text=True, check=False)
        assert res.returncode == 0, res.stdout + res.stderr


def test_gitignore_env_and_data_and_example_clean():
    for p in (".env", ".env.local", "data/demo/settings.yaml"):
        assert subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT, check=False).returncode == 0, p
    assert subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=ROOT, check=False).returncode == 1
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            assert line.split("=", 1)[1].strip() in ("", "your-youtube-api-key"), line


# ---- критерии 7-8: витрина ----

def _demo_numbers():
    rows = list(csv.DictReader((ROOT / "examples/demo/import.csv").read_text(encoding="utf-8").splitlines()))
    top = max(rows, key=lambda r: int(r["views"]))
    same = [int(r["views"]) for r in rows
            if r["channel_id"] == top["channel_id"] and r["id"] != top["id"]]
    norm = statistics.median(same)
    return top, int(top["views"]), norm, int(top["views"]) / norm


def test_site_example_numbers_recomputed_from_demo():
    top, views, norm, ratio = _demo_numbers()
    fmt = lambda n: f"{int(n):,}".replace(",", " ")
    assert top["title"] in SITE
    row = re.search(r"<tr><td>[^<]*</td>.*?</tr>", SITE.split("<tbody>")[1], re.DOTALL).group(0)
    assert fmt(views) in row and fmt(norm) in row and f"×{ratio:.2f}" in row


def test_site_example_brief_taken_from_demo_brief():
    brief = (ROOT / "examples/demo/expected/briefs/01.md").read_text(encoding="utf-8")
    title = re.search(r"^# (.+)$", brief, re.MULTILINE).group(1)
    assert title in SITE
    for key in ("Идея:", "Первые 15 секунд:", "Название 1:", "Чем отличаемся:"):
        m = re.search(rf"^- {re.escape(key)} (.+)$", brief, re.MULTILINE)
        assert m, key
        text = m.group(1).split(". На экране")[0].split(" Сохраняем")[0]
        text = text.removeprefix("залёт ")  # на витрине здесь вставлено название залёта
        norm = re.sub(r"\s+", " ", text)[:40]
        assert norm.lower() in SITE.lower(), (key, norm)


def test_site_texts_and_no_external_resources():
    assert "Пример на демо-данных, не реальный канал" in SITE
    assert "Если GitHub не открывается, попробуйте позже" in SITE
    assert SITE.count("https://github.com/ozerova152-lab/youtube-producer") >= 2
    assert re.search(r"<code[^>]*>https://github\.com/ozerova152-lab/youtube-producer</code>", SITE)
    for m in re.finditer(r'<(script|link|img|iframe)\b[^>]*?(?:src|href)="([^"]+)"', SITE):
        assert not m.group(2).startswith(("http:", "https:", "//")), m.group(0)
    assert not re.search(r"cdn\.|googleapis|jsdelivr|unpkg", SITE)
    assert not SECRET_RE.search(SITE)


def test_site_no_hex_or_arbitrary_px_and_size():
    css_and_html = SITE
    assert not re.search(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b(?![\w-])", re.sub(r'href="#[^"]*"|id="[^"]*"', "", css_and_html))
    assert "style=" not in SITE
    total = sum(f.stat().st_size for f in (ROOT / "site").rglob("*") if f.is_file())
    assert total < 1_000_000


def test_phone_360_no_horizontal_scroll_and_no_js_no_css():
    from playwright.sync_api import sync_playwright
    url = (ROOT / "site/index.html").as_uri()
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            ctx = b.new_context(viewport={"width": 360, "height": 740})
            page = ctx.new_page()
            page.goto(url)
            assert page.evaluate("document.documentElement.scrollWidth <= 360")
            assert page.get_by_text("Пример на демо-данных, не реальный канал").is_visible()
            ctx.close()
            ctx = b.new_context(viewport={"width": 360, "height": 740}, java_script_enabled=False)
            page = ctx.new_page()
            page.goto(url)
            assert page.get_by_text("Если GitHub не открывается, попробуйте позже").is_visible()
            assert page.get_by_text("×12.68").is_visible()
            ctx.close()
            ctx = b.new_context(viewport={"width": 360, "height": 740})
            page = ctx.new_page()
            page.route("**/*.css", lambda r: r.abort())
            page.goto(url)
            assert page.get_by_text("Если GitHub не открывается, попробуйте позже").is_visible()
            assert page.get_by_text("https://github.com/ozerova152-lab/youtube-producer").first.is_visible()
            ctx.close()
        finally:
            b.close()
