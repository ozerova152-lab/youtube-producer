"""T30, независимая проверка: ссылки и якоря, паритет RU/EN, статус «проверен» в одном месте,
висячие ссылки на удалённые разделы, демо-команды из README во временной копии."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
README_EN = (ROOT / "README.en.md").read_text(encoding="utf-8")
MD_FILES = [ROOT / "README.md", ROOT / "README.en.md"] + sorted((ROOT / "docs").glob("*.md"))


def _slug(heading):
    """GitHub-якорь: нижний регистр, без знаков, пробелы в дефисы (кириллица сохраняется)."""
    s = re.sub(r"`|\*|<[^>]+>", "", heading).strip().lower()
    s = re.sub(r"[^\w\- ]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def _anchors(path):
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return {_slug(m.group(1)) for m in re.finditer(r"^#{1,6} (.+)$", text, re.MULTILINE)}


def _links(path):
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return re.findall(r"\]\(([^)\s]+)\)", text)


@pytest.mark.parametrize("md", MD_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_and_anchors_alive(md):
    for link in _links(md):
        if re.match(r"(https?:|mailto:)", link):
            continue
        target, _, frag = link.partition("#")
        path = (md.parent / target).resolve() if target else md
        assert path.exists(), f"{md.name}: битая ссылка {link}"
        if frag and path.suffix == ".md":
            assert frag in _anchors(path), f"{md.name}: нет якоря {link} (есть {sorted(_anchors(path))})"


def test_readme_en_structure_matches_ru():
    steps_ru = re.findall(r"^### Шаг (\d)\.", README, re.MULTILINE)
    steps_en = re.findall(r"^### Step (\d)\.", README_EN, re.MULTILINE)
    assert steps_ru == steps_en == ["1", "2", "3", "4", "5"]
    assert len(re.findall(r"^## ", README, re.MULTILINE)) == len(re.findall(r"^## ", README_EN, re.MULTILINE))
    assert README_EN.count("**What to do:**") == README.count("**Что сделать:**") == 5
    assert README_EN.count("**What you will see:**") == README.count("**Что увидите:**") == 5
    assert README_EN.count("**If it did not work:**") == README.count("**Если не получилось:**") == 5
    # те же команды и числа
    for token in ("python3 --version", "make setup", "make add-key", "Ubuntu-24.04", "3.12",
                  "git clone https://github.com/ozerova152-lab/youtube-producer.git"):
        assert token in README and token in README_EN, token
    # docs на русском помечены
    assert "in Russian" in README_EN
    # EN-версия не уходит на русский WSL-файл
    assert "docs/windows-wsl.md" not in README_EN
    assert "docs/windows-wsl.en.md" in README_EN


def test_wsl_ru_en_parity():
    ru = (ROOT / "docs/windows-wsl.md").read_text(encoding="utf-8")
    en = (ROOT / "docs/windows-wsl.en.md").read_text(encoding="utf-8")
    for cmd in ("wsl --install", "wsl --install --web-download -d Ubuntu", "wsl --install -d Ubuntu-24.04",
                "python3 --version", "/mnt/c"):
        assert cmd in ru and cmd in en, cmd
    stuck_ru = ru[ru.index("Если застряли"):ru.index("## Где держать")]
    stuck_en = en[en.index("If you get stuck"):en.index("## Where to keep")]
    assert len(re.findall(r"^- \*\*", stuck_ru, re.MULTILINE)) == len(re.findall(r"^- \*\*", stuck_en, re.MULTILINE)) == 5


def test_agent_status_words_live_only_in_compatibility():
    """Статус «проверен» по агентам дан один раз: в README и прочих docs его нет."""
    pat = re.compile(r"\bпровер(ен|ена|ено|ены)\b|\bне проверяли\b|\bnot tested\b|\btested\b|\bverified\b", re.IGNORECASE)
    offenders = []
    for md in MD_FILES:
        if md.name == "compatibility.md":
            continue
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line) and "dev/" not in str(md):
                offenders.append(f"{md.relative_to(ROOT)}:{i}: {line.strip()[:100]}")
    assert offenders == [], offenders


def test_compatibility_is_single_source_for_statuses():
    comp = (ROOT / "docs/compatibility.md").read_text(encoding="utf-8")
    for phrase in ("Основной путь — Claude Code, проверен полностью.", "Cowork мы не проверяли"):
        assert phrase in comp
    assert comp.count("Основной путь") == 1


def test_no_dangling_references_to_removed_readme_sections():
    gone = ["Установка и запуск", "#установка", "#windows-как-поставить-wsl", "#слова-которые-встретятся",
            "#безопасность", "#сколько-времени", "Сколько времени и подписки", "#для-чего-проект-не-подходит"]
    scan = ["AGENTS.md", "CLAUDE.md", "playbooks", ".claude", "docs", "src", "site", "templates", "README.md",
            "README.en.md", "examples"]
    hits = []
    for rel in scan:
        base = ROOT / rel
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()] if base.exists() else []
        for f in files:
            if "docs/tasks" in str(f) or f.suffix in {".pyc", ".jpg", ".png", ".woff2"} or ".venv" in f.parts:
                continue
            try:
                t = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for g in gone:
                if g in t:
                    hits.append(f"{f.relative_to(ROOT)}: {g}")
    assert hits == [], hits


def test_step3_order_and_branches_en_too():
    for text, a, b in ((README, "### Шаг 3.", "### Шаг 4."), (README_EN, "### Step 3.", "### Step 4.")):
        s = text[text.index(a):text.index(b)]
        assert s.index("python3 --version") < s.index("make setup")
        assert "python.org/downloads" in s and "Mac" in s and "Ubuntu" in s and "24.04" in s


def test_readme_demo_commands_work_in_temp_copy(tmp_path):
    """Три команды из блока «Попробовать без ключа» выполняются дословно вне репозитория."""
    produce = ROOT / ".venv/bin/produce"
    if not produce.exists():
        pytest.skip("нет .venv")
    block = README[README.index("## Попробовать без ключа"):README.index("## Свой канал")]
    cmds = re.findall(r"```bash\n(.*?)```", block, re.DOTALL)[0].strip().splitlines()
    work = tmp_path / "proj"
    work.mkdir()
    shutil.copytree(ROOT / "examples", work / "examples")
    (work / ".venv/bin").mkdir(parents=True)
    (work / ".venv/bin/produce").symlink_to(produce)
    outs = []
    for c in cmds:
        r = subprocess.run(c, check=False, shell=True, cwd=work, capture_output=True, text=True)
        assert r.returncode == 0, (c, r.stdout, r.stderr)
        outs.append(r.stdout)
    assert "Загружено: 11 видео, 2 канала. Обращений к YouTube: 0" in outs[1]
    assert "Как использовать нейросеть: выпуск 1" in outs[2] and "12.68" in outs[2]
    assert len(re.findall(r"Как использовать нейросеть|залёт", outs[2])) >= 1
