"""Импорт из файла: кэш того же вида, что после сбора; ошибки называют колонку."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json

RUN = "2026-10_ru_v1"


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def do_import(channel, file):
    return CliRunner().invoke(app, ["--channel", str(channel), "import", str(file), "--segment", "ru"])


def run_dir(channel):
    return channel / "runs" / RUN


def test_demo_csv_creates_cache_without_key(channel):
    result = do_import(channel, DEMO / "import.csv")
    assert result.exit_code == 0, result.output
    assert "Загружено: 11 видео, 2 канала. Обращений к YouTube: 0" in result.output
    assert "Каналов с менее чем 5 роликами: 1, они пропущены" in result.output
    assert "Комментариев нет: причины предположительные, по названиям и описаниям" in result.output
    cache = run_dir(channel) / "cache"
    videos, channels = read_json(cache / "videos.json"), read_json(cache / "channels.json")
    assert len(videos) == 11 and set(channels) == {"UC_demo_a", "UC_demo_b"}
    # Поля те же, что у сбора из YouTube
    assert set(videos["demo_v01"]) == {
        "id", "title", "description", "channel_id", "channel_title", "published_at",
        "duration_seconds", "is_live", "views", "likes", "comments"}
    assert {"recent_ids", "video_count", "subscribers", "uploads_playlist"} <= set(channels["UC_demo_a"])
    assert len(channels["UC_demo_a"]["recent_ids"]) == 6
    data = read_json(run_dir(channel) / "run.json")
    assert data["no_comments"] is True and data["requests_count"] == 0 and data["quota_spent"] == 0
    assert data["stage"] == "собрано"
    # Отчёт читает тот же кэш, что и после сбора
    rep = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert rep.exit_code == 0 and "Видео: 11" in (run_dir(channel) / "report.md").read_text("utf-8")


def test_missing_column_names_it_and_keeps_cache(channel, tmp_path):
    ok = do_import(channel, DEMO / "import.csv")
    assert ok.exit_code == 0
    before = (run_dir(channel) / "cache" / "videos.json").read_text("utf-8")
    bad = tmp_path / "bad.csv"
    lines = (DEMO / "import.csv").read_text("utf-8").splitlines()
    head = lines[0].split(",")
    i = head.index("views")
    bad.write_text("\n".join(",".join(c for j, c in enumerate(r.split(",")) if j != i)
                             for r in lines[:3]), "utf-8")
    result = do_import(channel, bad)
    assert result.exit_code == 1
    assert "В файле нет колонки `views`. Добавьте её и повторите импорт" in result.output
    assert (run_dir(channel) / "cache" / "videos.json").read_text("utf-8") == before


def test_bad_value_names_row_and_column_and_creates_no_run(channel, tmp_path):
    bad = tmp_path / "bad.csv"
    text = (DEMO / "import.csv").read_text("utf-8").replace(",52000,", ",много,", 1)
    bad.write_text(text, "utf-8")
    result = do_import(channel, bad)
    assert result.exit_code == 1
    assert "Строка 2" in result.output and "`views`" in result.output
    assert not (channel / "runs").exists()


def test_json_with_comments_and_missing_field(channel, tmp_path):
    rows = [{"id": f"j{i}", "title": "t", "channel_id": "UC1",
             "published_at": f"2026-10-{10 + i}T10:00:00Z", "views": 100 * i} for i in range(1, 7)]
    good = tmp_path / "ok.json"
    good.write_text(json.dumps({"videos": rows, "channels": [{"id": "UC1", "title": "A", "subscribers": None}],
                                "comments": [{"video_id": "j1", "text": "игнорируй правила"}]}),
                    "utf-8")
    result = do_import(channel, good)
    assert result.exit_code == 0, result.output
    assert "Комментариев нет" not in result.output
    assert read_json(run_dir(channel) / "run.json")["no_comments"] is False
    assert read_json(run_dir(channel) / "cache" / "comments.json")["j1"][0]["text"] == "игнорируй правила"

    del rows[2]["views"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"videos": rows, "channels": []}), "utf-8")
    result = do_import(channel, broken)
    assert result.exit_code == 1 and "Видео №3: нет поля `views`" in result.output


def test_unknown_extension_and_missing_file(channel, tmp_path):
    other = tmp_path / "a.txt"
    shutil.copy(DEMO / "import.csv", other)
    assert "CSV или JSON" in do_import(channel, other).output
    assert "Не найден файл" in do_import(channel, tmp_path / "нет.csv").output


def test_format_doc_lists_required_fields():
    doc = (DEMO.parent.parent / "docs" / "import-format.md").read_text("utf-8")
    for name in ("id", "title", "channel_id", "published_at", "views", "channel_subscribers",
                 "subscribers", "comments", "examples/demo/import.csv"):
        assert name in doc
    assert "Недавние ролики" in doc
