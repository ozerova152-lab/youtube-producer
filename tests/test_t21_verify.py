"""T21, независимая проверка по критериям приёмки: AGENTS.md + CLAUDE.md, README, скиллы, make, демо."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
SETUP = (ROOT / "docs/dev/setup.md").read_text(encoding="utf-8")


def _section(text, title):
    m = re.search(rf"^## {re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, title
    return m.group(1)


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


# --- 1-2: AGENTS.md / CLAUDE.md ---------------------------------------------------------------

def test_agents_has_all_old_claude_rules():
    # c90108e — коммит T21; его родитель хранит прежний CLAUDE.md до разделения на два файла
    old = subprocess.run(["git", "show", "c90108e~1:CLAUDE.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    # каждая строка-правило старого CLAUDE.md, кроме Claude-специфичной, есть в AGENTS.md
    lines = [l.strip() for l in old.splitlines() if l.strip().startswith(("- ", "| `"))]
    missing = [l for l in lines if l not in AGENTS and "Мини-скиллы" not in l and "settings.json" not in l
               and not l.startswith("| `make setup`") and not l.startswith("| `make check`")]
    assert missing == [], missing


def test_claude_imports_agents_and_has_no_duplicate_sentences():
    assert CLAUDE.splitlines()[0].strip() == "@AGENTS.md"
    # на уровне предложений и строк, строже, чем «абзац»
    def pieces(t):
        out = set()
        for line in t.splitlines():
            for s in re.split(r"(?<=[.;])\s+", line.strip()):
                s = _norm(s)
                if len(s) >= 30:
                    out.add(s)
        return out
    dup = pieces(CLAUDE) & pieces(AGENTS)
    assert dup == set(), dup
    assert "settings.json" in CLAUDE and "Мини-скиллы" in CLAUDE
    assert "settings.json" not in AGENTS  # Claude-специфичное не утекло в общий файл


# --- 3-4, 7-8: README -------------------------------------------------------------------------

def test_quickstart_three_steps_and_key_later():
    qs = _section(README, "Быстрый старт")
    assert len(re.findall(r"^\d\. ", qs, re.MULTILINE)) == 3
    assert "make setup" in qs and "запусти месяц" in qs
    assert "позже" in qs and "демо" in qs
    # быстрый старт на первом экране: до любого другого `## `
    assert README.index("## Быстрый старт") < README.index("## Безопасность")


def test_three_paths_have_phrases_and_marks():
    cc = _section(README, "Claude Code")
    cw = _section(README, "Claude Cowork")
    cx = _section(README, "Codex")
    assert "запусти месяц" in cc and "продолжи месяц" in cc and "проверен" in cc.lower()
    for s in (cw, cx):
        assert "Прочитай AGENTS.md и запусти месяц" in s and "Прочитай AGENTS.md и продолжи месяц" in s
    assert "Не проверено" in cw
    assert "не сверяли" in cx.lower() or "не проверял" in cx.lower() or "лишь на базовом" in cx
    # Cowork и Codex не названы «проверенными полностью»
    assert "проверен полностью" not in cw.lower() and "проверен полностью" not in cx.lower()


def test_security_before_cowork_codex_and_honest():
    sec_i = README.index("\n## Безопасность")
    assert sec_i < README.index("\n## Claude Cowork") and sec_i < README.index("\n## Codex")
    sec = _section(README, "Безопасность")
    for p in ("только в Claude Code", ".claude/settings.json", "автоподтверждение", "не вставляйте ключ в чат"):
        assert p in sec, p


def test_placeholder_address_line_untouched():
    before = subprocess.run(["git", "show", "HEAD:README.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    line = next(l for l in before.splitlines() if l.startswith("Адрес репозитория"))
    assert line in README.splitlines()


def test_demo_section_commands_and_expected_result():
    demo = _section(README, "Демо без ключа")
    assert "examples/demo/import_comments.json" in demo and "virals" in demo and "×12.68" in demo
    assert (ROOT / "examples/demo/import_comments.json").is_file()


def test_troubleshooting_covers_all_cases():
    t = _section(README, "Если что-то не получилось").lower()
    for k in ("python3: command not found", "make: command not found", "make setup", "no space left",
              "ключ не подошёл", "квота", "агент не понимает"):
        assert k in t, k
    rows = [r for r in t.splitlines() if r.startswith("|") and not r.startswith("|--") and "что видите" not in r]
    assert len(rows) >= 6
    assert all(r.count("|") >= 3 and r.split("|")[2].strip() for r in rows)  # у каждого пункта есть «что сделать»


def test_glossary_words_and_size():
    g = _section(README, "Слова, которые встретятся")
    items = [l for l in g.splitlines() if l.startswith("- ")]
    assert 6 <= len(items) <= 8
    for w in ("залёт", "норма канала", "квота", "сегмент", "бриф", "стратегия", "запуск", "wsl"):
        assert any(w in i.lower().split("—")[0] for i in items), w


def test_no_invented_time_or_subscription_numbers():
    s = _section(README, "Сколько времени и подписки")
    assert "не измерено" in s and "не измерен" in s
    # числа допустимы только про квоту/обращения; ни минут, ни часов, ни рублей, ни долларов
    assert not re.search(r"\d+\s*(мин|час|ч\b|сек|₽|руб|\$|usd|%)", s, re.IGNORECASE), s
    # чужие утверждения без пометки: Cowork/Codex нигде не заявлены как работающие
    low = README.lower()
    assert "cowork работает" not in low and "codex работает" not in low


def test_no_personal_data():
    for name in ("README.md", "AGENTS.md", "CLAUDE.md", "docs/dev/setup.md", "Makefile", "playbooks/README.md",
                 ".claude/skills/start-month/SKILL.md", ".claude/skills/continue-month/SKILL.md",
                 ".claude/skills/demo/SKILL.md", ".claude/skills/setup-check/SKILL.md"):
        t = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"/home/|matebook|UCZ0|AIza[0-9A-Za-z_-]{10}|C:\\Users", t), name
        assert not re.search(r"\bUC[\w-]{22}\b", t), name


# --- 9, 12: скиллы ----------------------------------------------------------------------------

def _skill(n):
    return (ROOT / ".claude/skills" / n / "SKILL.md").read_text(encoding="utf-8")


def test_setup_check_only_existence_of_env():
    t = _skill("setup-check")
    cmds = re.findall(r"`([^`]*)`", t)
    for c in cmds:
        if ".env" in c.replace(".env.example", ""):
            assert c == "test -f .env" or c.startswith("Read") is False and "cat" not in c, c
    # ни одной команды, читающей .env
    assert not re.search(r"\b(cat|head|tail|less|grep|sed|awk|source|\.)\s+[^`\n]*\.env\b", t.replace("test -f .env", ""))
    assert not re.search(r"export|dotenv|printenv|\benv\b\s*\|", t)


def test_demo_skill_safe():
    t = _skill("demo")
    assert t.index("test -d data/demo") < t.index("cp -r examples/demo data/demo")
    assert "rm " not in t and "make reset" in t  # reset упомянут только как вариант по слову человека
    assert "без его слова" in t.lower()


def test_readme_says_skills_optional():
    assert "Без них всё работает по фразам" in README


# --- 10: make ---------------------------------------------------------------------------------

def test_make_targets():
    user = subprocess.run(["make", "-n", "setup"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    dev = subprocess.run(["make", "-n", "setup-dev"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert "playwright" not in user and "[dev]" not in user
    assert "pip install -e ." in user
    assert "venv" in dev and "[dev]" in dev and "playwright install chromium" in dev


def test_setup_doc_consistent():
    assert "make setup-dev" in SETUP
    # «make check» нигде не описан как идущий после голого `make setup` в docs/dev и AGENTS
    for text in (SETUP, AGENTS):
        for line in text.splitlines():
            if "make check" in line and "make setup" in line:
                assert "setup-dev" in line, line
    # противоречие: setup не должен ставить Chromium по docs
    for line in SETUP.splitlines():
        if line.startswith("- `make setup` "):
            assert "не скачивается" in line


# --- 11: демо из README вживую, вне репозитория -----------------------------------------------

def test_readme_demo_commands_work_outside_repo(tmp_path):
    produce = ROOT / ".venv/bin/produce"
    if not produce.exists():
        pytest.skip("нет .venv")
    chan = tmp_path / "demo"
    shutil.copytree(ROOT / "examples/demo", chan)
    shutil.rmtree(chan / "runs", ignore_errors=True)

    def run(*a):
        return subprocess.run([str(produce), "--channel", str(chan), *a], check=False,
                              cwd=tmp_path, capture_output=True, text=True, timeout=120)
    r1 = run("start", "--segment", "ru", "--brief-lang", "ru")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = run("import", str(ROOT / "examples/demo/import_comments.json"), "--segment", "ru")
    assert r2.returncode == 0 and "Загружено: 11 видео, 2 канала" in r2.stdout and "Обращений к YouTube: 0" in r2.stdout
    r3 = run("virals", "--segment", "ru")
    assert r3.returncode == 0 and "12.68" in r3.stdout, r3.stdout
    assert "×4.39" in r3.stdout or "4.39" in r3.stdout
    # повторный импорт не ломается
    assert run("import", str(ROOT / "examples/demo/import_comments.json"), "--segment", "ru").returncode == 0
    # не-существующий файл: человеческая ошибка, код 1, без трейсбека
    r5 = run("import", str(tmp_path / "нет.json"), "--segment", "ru")
    assert r5.returncode == 1 and "Traceback" not in r5.stdout + r5.stderr
