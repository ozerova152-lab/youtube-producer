"""Доска docs/tasks/board.md сходится с файлами задач: ни одна задача не потеряна, счёт верный."""

import re
from pathlib import Path

import yaml

TASKS = Path(__file__).parent.parent / "docs" / "tasks"
ALLOWED = {"todo", "in_progress", "done", "needs_human", "cancelled"}


def _tasks():
    out = {}
    for path in sorted(TASKS.glob("T[0-9][0-9]-*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
        assert m, f"нет заголовка в {path.name}"
        meta = yaml.safe_load(m.group(1))
        out[meta["id"]] = (path, meta)
    return out


def test_every_task_file_has_valid_header():
    for tid, (path, meta) in _tasks().items():
        assert path.name.startswith(tid + "-"), path.name
        assert meta["status"] in ALLOWED, (tid, meta["status"])
        assert meta.get("summary"), tid
        assert isinstance(meta.get("acceptance"), list) and meta["acceptance"], tid


def test_board_lists_every_task_exactly_once_and_counts_match():
    board = (TASKS / "board.md").read_text(encoding="utf-8")
    tasks = _tasks()
    for tid in tasks:
        assert len(re.findall(rf"\*\*{tid}\*\*", board)) == 1, tid
    total = len(tasks)
    done = sum(1 for _, meta in tasks.values() if meta["status"] == "done")
    m = re.search(r"· (\d+) задач\S* · готово (\d+) из (\d+)", board)
    assert m, "нет строки со счётом на доске"
    assert (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (total, done, total)


def test_t22_is_parked_for_a_human_and_not_picked_up_automatically():
    path, meta = _tasks()["T22"]
    assert meta["status"] == "needs_human"  # автоматически (/build-tasks) не берётся
    assert meta["blocked_by"] == []
    text = path.read_text(encoding="utf-8")
    assert "позже" in text.lower()
    for item in ("settings.yaml", "Claude Cowork", "диск Windows"):
        assert item in text, item
    board = (TASKS / "board.md").read_text(encoding="utf-8")
    nh = board.split("## ⚠ Нужен человек")[1].split("\n## ")[0]
    assert "**T22**" in nh and "позже" in nh.lower()
