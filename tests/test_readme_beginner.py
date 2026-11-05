"""T30: README для новичка: пять шагов быстрого старта с тремя метками, разделы на месте, ссылки на docs живые."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
HEADINGS = ["## Что вы получите", "## Что понадобится", "## Быстрый старт", "## Попробовать без ключа",
            "## Свой канал", "## Если что-то не получилось", "## Подробнее", "## Лицензия"]
DOCS = ["windows-wsl.md", "windows-wsl.en.md", "compatibility.md", "glossary.md", "limits-and-security.md",
        "how-it-works.md", "chat-mode.md"]


def test_sections_in_order_and_short():
    pos = [README.index("\n" + h + "\n") for h in HEADINGS]
    assert pos == sorted(pos)
    assert len(README.splitlines()) <= 132


def test_quick_start_has_five_steps_with_three_labels():
    steps = re.findall(r"^### Шаг (\d)\. [^\n]*\n(.*?)(?=^### |^## )", README, re.DOTALL | re.MULTILINE)
    assert [n for n, _ in steps] == ["1", "2", "3", "4", "5"]
    for n, body in steps:
        for label in ("**Что сделать:**", "**Что увидите:**", "**Если не получилось:**"):
            assert label in body, (n, label)


def test_step3_python_check_before_make_setup_with_mac_branch():
    step3 = README[README.index("### Шаг 3."):README.index("### Шаг 4.")]
    assert step3.index("python3 --version") < step3.index("make setup")
    assert "python.org/downloads" in step3 and "Mac" in step3 and "Ubuntu" in step3


def test_removed_and_moved_content():
    assert "Сколько времени и подписки" not in README
    for gone in ("## Слова, которые встретятся", "## Безопасность", "### Windows: как поставить WSL",
                 "## Для чего проект не подходит"):
        assert gone not in README, gone


def test_docs_exist_and_are_linked_from_readme():
    for name in DOCS:
        assert (ROOT / "docs" / name).is_file(), name
    for name in DOCS:
        if name != "windows-wsl.en.md":
            assert f"docs/{name}" in README, name
    assert "docs/windows-wsl.en.md" in (ROOT / "README.en.md").read_text(encoding="utf-8")


def test_demo_block_has_three_commands_and_expected_line():
    demo = README[README.index("## Попробовать без ключа"):README.index("## Свой канал")]
    cmds = re.findall(r"```bash\n(.*?)```", demo, re.DOTALL)[0].strip().splitlines()
    assert len(cmds) == 3
    assert "Загружено: 11 видео, 2 канала. Обращений к YouTube: 0" in demo and "2 залёта" in demo
