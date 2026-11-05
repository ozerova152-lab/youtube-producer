"""T35 (независимая проверка): в спеке 01/02, compatibility.md и 03b-covers.md нет пометок о проверке по агентам;
смысл строк и запасной путь для обложек сохранены; agent-status.md остаётся единственным местом статуса."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


BAD = re.compile(
    r"проверен полностью|30\.10\.2026|не проверяли|не проверялись|не проверены|не пробовали|результат неизвестен|"
    r"Cowork мы не проверяли|Codex проверен|Проверено только|Cowork не проверя",
    re.IGNORECASE,
)


@pytest.mark.parametrize("rel", ["docs/spec/01-functional-requirements.md", "docs/spec/02-tech-architecture.md",
                                 "docs/compatibility.md", "playbooks/03b-covers.md", "AGENTS.md", "CLAUDE.md"])
def test_no_status_phrases(rel):
    assert not BAD.findall(read(rel)), (rel, BAD.findall(read(rel)))


def test_spec02_agent_line_keeps_meaning():
    line = next(x for x in read("docs/spec/02-tech-architecture.md").splitlines() if x.startswith("- ИИ — агент"))
    for need in ("Claude Code", "`AGENTS.md`", "Issues", "по его собственной подписке",
                 "ключей ИИ, API-ключа Claude, баланса и платы за ИИ в проекте нет"):
        assert need in line, need
    assert "Codex" not in line and "Cowork" not in line


def test_covers_fallback_and_requirements_kept():
    section = read("docs/compatibility.md").split("## Обложки залётов (шаг 3б)")[1].split("\n## ")[0]
    for need in ("https://i.ytimg.com/", "thumbs/", "<id видео>.jpg", "`.png`", "`.webp`", "«готово»", "«пропустить»",
                 "не каждый агент это умеет", "`data/`", "не попадают в git", "Скрипт картинки сам не скачивает"):
        assert need in section, need
    assert not re.search(r"проверен|пробовал|неизвестен", section, re.IGNORECASE)
    play = read("playbooks/03b-covers.md")
    for need in ("WebFetch", "Read", "https://i.ytimg.com/", "thumbs/<id видео>.jpg", "«готово»", "«пропустить»",
                 "Не каждый агент умеет открывать картинки", "запасн"):
        assert need in play, need
    head = play.split("## Как агент смотрит картинку")[1].split("\n")[2]
    assert not re.search(r"проверен|не пробовал", head, re.IGNORECASE)


def test_spec01_lines_consistent():
    t = read("docs/spec/01-functional-requirements.md")
    assert "Cowork не проверяли" not in t
    # пометок о проверке по агентам в строках про README/витрину нет
    for line in t.splitlines():
        if "Расскажите, как получилось" in line or "agent-status" in line:
            assert not re.search(r"не проверя|проверен полностью|проверен на", line, re.IGNORECASE), line
    # agent-status упомянут в спеке только как место хранения, и только в «Что НЕ делаем»
    assert t.count("agent-status.md") == 1 and "служебной заметке" in t


def test_agent_status_only_referenced_from_spec():
    ok = {"docs/spec/01-functional-requirements.md", "docs/spec/02-tech-architecture.md"}
    files = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], text=True, cwd=ROOT).split("\n")
    for rel in files:
        if not rel.endswith((".md", ".html")) or rel.startswith(("docs/tasks/", ".claude/")) or rel in ok:
            continue
        if rel in ("docs/dev/agent-status.md",):
            continue
        assert "agent-status" not in read(rel), rel


def test_agent_status_untouched_since_t34():
    try:
        diff = subprocess.check_output(["git", "diff", "b41cf84", "--", "docs/dev/agent-status.md"], text=True,
                                       cwd=ROOT, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("нет истории git с коммитом T34")
    assert diff == ""
    assert (ROOT / "docs/dev/agent-status.md").read_text(encoding="utf-8").strip()


def test_t34_verify_compares_with_fixed_parent_not_head():
    src = read("tests/test_t34_verify.py")
    assert "b41cf84~1:docs/compatibility.md" in src and "HEAD:docs/compatibility.md" not in src
    # фиксированный хэш осмыслен: родитель T34 содержит раздел «## Статус», т.е. сравнение не вырождено
    try:
        old = subprocess.check_output(["git", "show", "b41cf84~1:docs/compatibility.md"], text=True, cwd=ROOT,
                                      stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("нет истории git")
    assert "## Статус\n\n" in old and "Cowork мы не проверяли" in old
