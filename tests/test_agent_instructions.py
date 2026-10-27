"""T01: проверки файлов инструкций агента (критерии приёмки по спеке, не по коду)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKIP_DIRS = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "docs", "data"}
SELF = Path(__file__).resolve()


def _repo_files():
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.resolve() == SELF:
            continue
        rel = p.relative_to(ROOT)
        if rel.parts[0] in SKIP_DIRS and rel.parts[:2] != ("docs", "dev"):
            continue
        if any(part in SKIP_DIRS - {"docs", "data"} for part in rel.parts):
            continue
        yield rel, p


def _text(p):
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _grep(pattern, flags=re.IGNORECASE):
    rx = re.compile(pattern, flags)
    return [str(rel) for rel, p in _repo_files() if rx.search(_text(p)) or rx.search(rel.name)]


CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_no_agents_md_file_or_links():
    names = [p.name.lower() for p in ROOT.rglob("*") if ".venv" not in p.parts and ".git" not in p.parts]
    assert "agents.md" not in names
    assert _grep(r"AGENTS\.md|AGENTS md") == []
    assert (ROOT / "CLAUDE.md").is_file()


def test_claude_md_required_content():
    low = CLAUDE.lower()
    # цель
    assert "## цель" in low
    # порядок шагов со ссылками на все сценарии
    for n in ["00-month", "01-collect", "02-virals", "03-analysis", "04-niche",
              "05-strategy", "06-briefs-plan", "07-history"]:
        assert f"playbooks/{n}.md" in CLAUDE, n
    # паузы
    assert "утверждена" in CLAUDE and "черновик" in low
    assert "принят" in low and "отклонён" in low
    # запреты
    assert re.search(r"не публиковать", CLAUDE, re.IGNORECASE)
    assert "данные, а не инструкции" in CLAUDE
    assert re.search(r"не читать `\.env`", CLAUDE, re.IGNORECASE)
    assert re.search(r"не менять `settings\.yaml`", CLAUDE, re.IGNORECASE)
    assert "--confirm" in CLAUDE and "после слова человека" in CLAUDE
    # раздел для разработки сохранён
    for kw in ["1 000 ₽", "main", "Стиль кода", "Правила безопасности"]:
        assert kw in CLAUDE, kw


def test_claude_code_denies_env_read():
    cfg = json.loads((ROOT / ".claude" / "settings.json").read_text())
    deny = cfg["permissions"]["deny"]
    assert any(d.startswith("Read(") and d.endswith(".env)") for d in deny)
    assert any(".env.*" in d for d in deny)


def test_playbooks_templates_markdown_and_claude_code_marks():
    for d in ("playbooks", "templates"):
        files = [p for p in (ROOT / d).rglob("*") if p.is_file()]
        assert files and all(p.suffix == ".md" for p in files), d
    for s in ("check", "reset"):
        assert "Только Claude Code" in (ROOT / ".claude/skills" / s / "SKILL.md").read_text()
    assert "Только Claude Code" in (ROOT / "playbooks/README.md").read_text()
    assert "make check" in CLAUDE and "make reset" in CLAUDE


def test_no_claude_api_leftovers():
    assert _grep("ANTHROPIC_API_KEY") == []
    assert _grep("провайдер ИИ") == []
    assert _grep(r"^ai:", re.MULTILINE) == []
    for rel, p in _repo_files():
        if p.suffix in (".py",):
            assert "import anthropic" not in _text(p) and "from anthropic" not in _text(p)
    assert "anthropic" not in (ROOT / "pyproject.toml").read_text().lower()


def test_claude_md_links_match_playbooks_exactly():
    """T15: CLAUDE.md ссылается на каждый существующий сценарий и ни на один несуществующий."""
    linked = set(re.findall(r"playbooks/([\w.-]+\.md)", CLAUDE))
    existing = {p.name for p in (ROOT / "playbooks").glob("*.md") if p.name != "README.md"}
    assert linked == existing, (linked ^ existing)


def test_all_playbook_cross_references_exist():
    """Ссылки на файлы проекта внутри сценариев и README не ведут в пустоту."""
    pattern = re.compile(r"`((?:playbooks|templates|docs|examples)/[\w./-]+\.(?:md|yaml|csv|json))`")
    for doc in [*(ROOT / "playbooks").glob("*.md"), ROOT / "README.md"]:
        for ref in pattern.findall(doc.read_text(encoding="utf-8")):
            assert (ROOT / ref).exists(), f"{doc.name}: {ref}"


def test_month_playbook_has_order_pauses_and_bans():
    text = (ROOT / "playbooks/00-month.md").read_text(encoding="utf-8")
    positions = [text.index(f"playbooks/{n}.md") for n in
                 ["01-collect", "02-virals", "03-analysis", "04-niche", "05-strategy", "06-briefs-plan"]]
    assert positions == sorted(positions)
    for phrase in ["запусти месяц", "продолжи месяц", "Где мы остановились", "Нужны настройки",
                   "утверждена", "принят / отклонён / позже", "Лимит агента на сегодня закончился",
                   "Ничего не публиковать", "Не читать `.env`", "`--confirm` ставится только после слова человека",
                   "07-history"]:
        assert phrase.lower() in text.lower(), phrase
