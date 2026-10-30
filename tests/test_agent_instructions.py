"""T01/T21: проверки файлов инструкций агента (критерии приёмки по спеке, не по коду).

T21: общие правила лежат в `AGENTS.md`, `CLAUDE.md` только подключает их и держит Claude-специфичное.
"""

import fnmatch
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


AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def _paragraphs(text):
    return {p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 40}


def test_agents_md_is_shared_file_and_claude_md_imports_it():
    """T21 (раньше тут требовалось, чтобы AGENTS.md не было): теперь он основа, CLAUDE.md его подключает."""
    assert (ROOT / "AGENTS.md").is_file() and (ROOT / "CLAUDE.md").is_file()
    assert CLAUDE_MD.splitlines()[0].strip() == "@AGENTS.md"
    # CLAUDE.md не повторяет текст правил: ни один абзац не встречается в обоих файлах
    assert _paragraphs(CLAUDE_MD) & _paragraphs(AGENTS) == set()
    # Claude-специфичное лежит в CLAUDE.md, а не в общем файле
    assert "Только Claude Code" in CLAUDE_MD and ".claude/settings.json" in CLAUDE_MD
    for skill in ("/start-month", "/continue-month", "/demo", "/setup-check"):
        assert f"`{skill}`" in CLAUDE_MD, skill
        assert f"`{skill}`" not in AGENTS, skill


def test_agents_md_required_content():
    CLAUDE = AGENTS
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


def test_claude_code_denies_env_read_through_shell_and_settings_edit():
    """Запрет `Read` обходится командой `cat .env`, а `settings.yaml` агент менять не должен."""
    deny = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["deny"]
    for command in ("cat", "head", "tail", "less", "grep", "sed", "awk"):
        assert any(d.startswith(f"Bash({command} ") and ".env" in d for d in deny), command
    assert any(d.startswith("Edit(") and d.endswith("settings.yaml)") for d in deny)
    assert any(d.startswith("Write(") and d.endswith("settings.yaml)") for d in deny)


def _shell_blocked(command, deny):
    """Модель правил Claude Code: шаблон `Bash(...)` сравнивается с командой целиком, `*` — любой текст."""
    return any(
        fnmatch.fnmatchcase(command, d[len("Bash("):-1]) for d in deny if d.startswith("Bash(")
    )


def test_env_shell_deny_blocks_reading_env_but_not_os_environ():
    deny = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["deny"]
    for command in (
        "cat .env", "cat ./.env", "cat data/mine/.env", "head -n 2 .env", "grep KEY .env",
        "grep KEY .env | head", "tail -n 1 .env.local", "sed -n 1p .env.example",
        "awk '{print}' .env", "less .env",
    ):
        assert _shell_blocked(command, deny), command
    for command in (
        "grep -rn os.environ src", "grep -nE 'getenv|os.environ' scripts/make_demo_cassettes.py",
        "grep -n environ src/produce/cli.py", "cat README.md",
        "sed -n 1,5p src/produce/core/settings.py",
    ):
        assert not _shell_blocked(command, deny), command


def test_playbooks_templates_markdown_and_claude_code_marks():
    for d in ("playbooks", "templates"):
        files = [p for p in (ROOT / d).rglob("*") if p.is_file()]
        assert files and all(p.suffix == ".md" for p in files), d
    for s in ("check", "reset"):
        assert "Только Claude Code" in (ROOT / ".claude/skills" / s / "SKILL.md").read_text()
    assert "Только Claude Code" in (ROOT / "playbooks/README.md").read_text()
    assert "make check" in AGENTS and "make reset" in AGENTS
    for s in ("start-month", "continue-month", "demo", "setup-check"):
        assert "Только Claude Code" in (ROOT / ".claude/skills" / s / "SKILL.md").read_text(encoding="utf-8"), s


def test_no_claude_api_leftovers():
    assert _grep("ANTHROPIC_API_KEY") == []
    assert _grep("провайдер ИИ") == []
    assert _grep(r"^ai:", re.MULTILINE) == []
    for rel, p in _repo_files():
        if p.suffix in (".py",):
            assert "import anthropic" not in _text(p) and "from anthropic" not in _text(p)
    assert "anthropic" not in (ROOT / "pyproject.toml").read_text().lower()


def test_agents_md_links_match_playbooks_exactly():
    """T15: AGENTS.md ссылается на каждый существующий сценарий и ни на один несуществующий."""
    linked = set(re.findall(r"playbooks/([\w.-]+\.md)", AGENTS))
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


def _skill(name):
    return (ROOT / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_setup_check_never_reads_env_content():
    """T21: /setup-check узнаёт только факт наличия `.env`, содержимое не читает и не печатает."""
    text = _skill("setup-check")
    assert "test -f .env" in text
    for bad in (r"cat\s+\S*\.env", r"grep\s+\S*\s*\S*\.env", r"head\s+\S*\.env", r"source\s+\S*\.env",
                r"Read\(", r"YOUTUBE_API_KEY="):
        assert not re.search(bad, text), bad
    assert "содержимое" in text and "не читай" in text


def test_demo_skill_does_not_overwrite_existing_demo():
    text = _skill("demo")
    assert "test -d data/demo" in text and "не затирай" in text
    assert "cp -r examples/demo data/demo" in text
    assert "rm -rf" not in text


def test_month_skills_point_to_month_playbook():
    assert "playbooks/00-month.md" in _skill("start-month")
    assert "playbooks/00-month.md" in _skill("continue-month")
    assert "продолжи месяц" in _skill("continue-month")


def test_readme_security_precedes_cowork_and_codex_and_states_env_limit():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sec = readme.index("\n## Безопасность")
    assert sec < readme.index("\n## Claude Cowork") and sec < readme.index("\n## Codex")
    block = readme[sec:readme.index("\n## ", sec + 5)]
    assert ".claude/settings.json" in block and "только в Claude Code" in block
    assert "автоподтверждение" in block and "не вставляйте ключ в чат" in block
    assert "Адрес репозитория: `https://github.com/ozerova152-lab/youtube-producer` (заглушка до публикации" in readme
