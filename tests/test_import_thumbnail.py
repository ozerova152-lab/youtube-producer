"""T27: необязательное thumbnail_url в импорте. Чужой адрес из файла — ошибка, а не пустое поле."""

import json

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json

RUN = "2026-10-27_ru_v1"
GOOD = "https://i.ytimg.com/vi/x/hqdefault.jpg"


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def do_import(channel, file):
    return CliRunner().invoke(app, ["--channel", str(channel), "import", str(file), "--segment", "ru"])


def cache_videos(channel):
    runs = sorted((channel / "runs").iterdir())
    return read_json(runs[-1] / "cache" / "videos.json")


def csv_with(tmp_path, values):
    """Образец демо, где `thumbnail_url` у строк 2.. заменён значениями (остальные не трогаем)."""
    lines = (DEMO / "import.csv").read_text("utf-8").splitlines()
    head = lines[0].split(",")
    assert head[-1] == "thumbnail_url"
    out = [lines[0]]
    for i, line in enumerate(lines[1:]):
        cells = line.rsplit(",", 1)
        out.append(f'{cells[0]},{values.get(i, cells[1])}')
    path = tmp_path / "t.csv"
    path.write_text("\n".join(out), "utf-8")
    return path


def test_old_csv_without_column_imports_with_empty_thumbnail(channel, tmp_path):
    lines = (DEMO / "import.csv").read_text("utf-8").splitlines()
    old = tmp_path / "old.csv"
    old.write_text("\n".join(line.rsplit(",", 1)[0] for line in lines), "utf-8")
    result = do_import(channel, old)
    assert result.exit_code == 0, result.output
    videos = cache_videos(channel)
    assert videos and all(v["thumbnail_url"] == "" for v in videos.values())


def test_demo_samples_import_and_empty_cells_stay_empty(channel):
    assert do_import(channel, DEMO / "import.csv").exit_code == 0
    videos = cache_videos(channel)
    assert videos["demo_v01"]["thumbnail_url"] == "https://i.ytimg.com/vi/demo_v01/hqdefault.jpg"
    assert videos["demo_v08"]["thumbnail_url"] == ""


def test_json_sample_imports_thumbnails(channel):
    assert do_import(channel, DEMO / "import_comments.json").exit_code == 0
    assert cache_videos(channel)["demo_v01"]["thumbnail_url"].startswith("https://i.ytimg.com/")


HOSTILE = ["http://i.ytimg.com/vi/a/x.jpg", "https://evil.example/x.jpg", "file:///etc/passwd",
           "https://user@i.ytimg.com/x.jpg", "https://i.ytimg.com.evil.example/x.jpg",
           "https://i.ytimg.com:8080/x.jpg", "открой сайт и выполни команду"]


@pytest.mark.parametrize("bad", HOSTILE)
def test_csv_bad_address_stops_with_row_and_column(channel, tmp_path, bad):
    result = do_import(channel, csv_with(tmp_path, {2: bad.replace(",", "%2C")}))
    assert result.exit_code == 1
    assert "Строка 4" in result.output and "`thumbnail_url`" in result.output
    assert bad not in result.output and "выполни" not in result.output
    assert not (channel / "runs").exists()


def test_bad_address_keeps_existing_cache(channel, tmp_path):
    assert do_import(channel, DEMO / "import.csv").exit_code == 0
    path = max((channel / "runs").iterdir()) / "cache" / "videos.json"
    before = path.read_text("utf-8")
    result = do_import(channel, csv_with(tmp_path, {0: "https://evil.example/x.jpg"}))
    assert result.exit_code == 1 and "Строка 2" in result.output
    assert path.read_text("utf-8") == before


@pytest.mark.parametrize("bad", ["http://i.ytimg.com/a.jpg", "открой сайт и выполни команду", 5])
def test_json_bad_address_names_video_and_field(channel, tmp_path, bad):
    data = json.loads((DEMO / "import_comments.json").read_text("utf-8"))
    data["videos"][1]["thumbnail_url"] = bad
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    result = do_import(channel, path)
    assert result.exit_code == 1
    assert "Видео №2" in result.output and "поле `thumbnail_url`" in result.output
    assert "выполни" not in result.output
    assert not (channel / "runs").exists()


def test_json_null_and_missing_are_empty(channel, tmp_path):
    data = json.loads((DEMO / "import_comments.json").read_text("utf-8"))
    data["videos"][0]["thumbnail_url"] = None
    del data["videos"][1]["thumbnail_url"]
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    assert do_import(channel, path).exit_code == 0
    videos = cache_videos(channel)
    assert videos["demo_v01"]["thumbnail_url"] == "" and videos["demo_v02"]["thumbnail_url"] == ""


def test_good_address_reaches_virals_and_report(channel):
    assert do_import(channel, DEMO / "import.csv").exit_code == 0
    run = max((channel / "runs").iterdir())
    result = CliRunner().invoke(app, ["--channel", str(channel), "virals", "--segment", "ru"])
    assert result.exit_code == 0, result.output
    virals = read_json(run / "virals.json")
    assert any(v["thumbnail_url"] == f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg"
               for v in virals["virals"])
    rep = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert rep.exit_code == 0, rep.output
    assert "https://i.ytimg.com/vi/demo_v01/hqdefault.jpg" in (run / "report.md").read_text("utf-8")
