"""Независимая проверка T18: склонение «залёт» в выводе `produce comments`.

Считаем формы через сам CLI (CliRunner на копии демо-канала), а не через plural().
Сети нет: до YouTube дело не доходит (оценка) либо HTTP подменён.
"""

import json
import re

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core import youtube
from produce.core.files import read_json
from produce.core.youtube import YouTubeApi

RUN = "2026-10_ru_v1"


@pytest.fixture(autouse=True)
def world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(youtube, "pause", lambda s: None)


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("YOUTUBE_API_KEY=CANARY-KEY-do-not-leak-9f3a17\n", encoding="utf-8")
    return path


def invoke(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args, "--segment", "ru"])


def prepared(channel, n):
    """Запуск, где ровно n залётов и нет скачанных комментариев."""
    assert invoke(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    assert invoke(channel, "virals").exit_code == 0
    run = channel / "runs" / RUN
    vpath = run / "virals.json"
    data = read_json(vpath)
    data["virals"] = [{"id": f"vid{i:03d}"} for i in range(n)]
    vpath.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (run / "cache" / "comments.json").unlink(missing_ok=True)
    return run


FORMS = [(1, "залёт"), (2, "залёта"), (3, "залёта"), (4, "залёта"), (5, "залётов"),
         (8, "залётов"), (11, "залётов"), (12, "залётов"), (21, "залёт"),
         (22, "залёта"), (25, "залётов"), (101, "залёт"), (111, "залётов")]


@pytest.mark.parametrize("n, word", FORMS)
def test_estimate_line_declines_word(channel, env_file, n, word):
    prepared(channel, n)
    res = invoke(channel, "comments", "--env-file", str(env_file))
    assert res.exit_code == 0, res.output
    assert f"Комментарии {n} {word}: ~{n} ед. Докачать?" in res.output
    # строка целиком, без хвоста лишних форм
    line = next(x for x in res.output.splitlines() if x.startswith("Комментарии "))
    assert line == f"Комментарии {n} {word}: ~{n} ед. Докачать?"
    assert "Жду вашего «да»." in res.output.splitlines()[-1]


def test_old_wrong_forms_never_appear(channel, env_file):
    for n in (1, 2, 3, 4):
        run = prepared(channel, n) if n == 1 else prepared_again(channel, n)
        res = invoke(channel, "comments", "--env-file", str(env_file))
        assert not re.search(r"Комментарии 1 залёта|Комментарии [234] залётов", res.output)
        assert run.exists()


def prepared_again(channel, n):
    run = channel / "runs" / RUN
    vpath = run / "virals.json"
    data = read_json(vpath)
    data["virals"] = [{"id": f"vid{i:03d}"} for i in range(n)]
    vpath.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return run


def test_zero_virals_gives_human_error_not_estimate(channel, env_file):
    prepared(channel, 0)
    res = invoke(channel, "comments", "--env-file", str(env_file))
    assert res.exit_code == 1
    assert "Залётов нет: докачивать комментарии не у кого" in res.output
    assert "Комментарии 0" not in res.output and "Докачать?" not in res.output


def test_already_collected_branch_has_no_estimate(channel, env_file):
    run = prepared(channel, 3)
    (run / "cache" / "comments.json").write_text(
        json.dumps({f"vid{i:03d}": [] for i in range(3)}), encoding="utf-8")
    res = invoke(channel, "comments", "--env-file", str(env_file))
    assert res.exit_code == 0, res.output
    assert "Комментарии залётов уже собраны. Обращений к YouTube: 0" in res.output
    assert "Докачать?" not in res.output and "Жду вашего" not in res.output


@pytest.mark.parametrize("n, word", [(1, "залёт"), (2, "залёта"), (5, "залётов"),
                                     (11, "залётов"), (21, "залёт")])
def test_confirm_summary_declines_word(channel, env_file, monkeypatch, n, word):
    # сеть не нужна: подменяем сам запрос комментариев
    run = prepared(channel, n)

    monkeypatch.setattr(YouTubeApi, "comments", lambda self, vid, limit: [])
    res = invoke(channel, "comments", "--confirm", "--env-file", str(env_file))
    assert res.exit_code == 0, res.output
    assert re.search(rf"Комментарии собраны: {n} {word}, 0 комментариев\.", res.output), res.output
    assert run.exists()
