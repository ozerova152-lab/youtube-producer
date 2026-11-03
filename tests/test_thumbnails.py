"""T24: ссылки на обложки в кэше, залётах, моих результатах и отчёте (картинки не скачиваются)."""

import pytest
import yaml
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json
from produce.core.youtube import best_thumbnail

CANARY = "CANARY-KEY-do-not-leak-7f3a9c"
RUN = "2026-10_ru_v1"
NO_DATA = "обложка: нет данных"


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def invoke(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args])


def run_dir(channel):
    return channel / "runs" / RUN


def collect(channel, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"YOUTUBE_API_KEY={CANARY}\n", encoding="utf-8")
    done = invoke(channel, "collect", "--segment", "ru", "--env-file", str(env), "--confirm")
    assert done.exit_code == 0, done.output


def test_best_thumbnail_takes_best_available_size():
    full = {s: {"url": f"https://i.ytimg.com/vi/x/{s}.jpg"} for s in
            ("default", "medium", "high", "standard", "maxres")}
    assert best_thumbnail(full).endswith("/maxres.jpg")
    del full["maxres"]
    assert best_thumbnail(full).endswith("/standard.jpg")
    assert best_thumbnail({"default": {"url": "https://i.ytimg.com/vi/x/d.jpg"}}).endswith("/d.jpg")


@pytest.mark.parametrize("raw", [None, {}, "x", {"high": {}}, {"high": {"url": ""}}, {"high": None}])
def test_best_thumbnail_empty_when_nothing_usable(raw):
    assert best_thumbnail(raw) == ""


@pytest.mark.vcr("collect_ru.yaml")
def test_collect_saves_thumbnail_urls_without_extra_requests(channel, tmp_path):
    collect(channel, tmp_path)
    videos = read_json(run_dir(channel) / "cache" / "videos.json")
    assert videos["demoVid_a01"]["thumbnail_url"] == "https://i.ytimg.com/vi/demoVid_a01/maxresdefault.jpg"
    assert videos["demoVid_a02"]["thumbnail_url"] == "https://i.ytimg.com/vi/demoVid_a02/hqdefault.jpg"
    # YouTube не прислал thumbnails: поле пустое, сбор не сломан.
    assert videos["demoVid_c03"]["thumbnail_url"] == ""
    # Число обращений равно числу записей в кассете: новых запросов нет.
    cassette = yaml.safe_load((DEMO / "cassettes" / "collect_ru.yaml").read_text(encoding="utf-8"))
    assert read_json(run_dir(channel) / "run.json")["requests_count"] == len(cassette["interactions"])
    # Картинок нигде нет.
    assert not [p for p in channel.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]


@pytest.mark.vcr("collect_ru.yaml")
def test_virals_and_report_show_cover_links(channel, tmp_path):
    collect(channel, tmp_path)
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    virals = read_json(run_dir(channel) / "virals.json")["virals"]
    assert virals and all(v["thumbnail_url"].startswith("https://i.ytimg.com/") for v in virals)
    text = (run_dir(channel) / "report.md").read_text(encoding="utf-8")
    first = virals[0]
    row = next(ln for ln in text.splitlines() if first["url"] in ln)
    assert f"[обложка]({first['thumbnail_url']})" in row
    mine = read_json(run_dir(channel) / "my_results.json")
    assert all(v["thumbnail_url"] for v in mine["best"] + mine["weak"])
    mine_text = text.split("## Мои результаты", 1)[1]
    assert f"[обложка]({mine['best'][0]['thumbnail_url']})" in mine_text
    assert CANARY not in text


@pytest.mark.vcr("collect_ru.yaml")
def test_old_cache_without_field_is_readable(channel, tmp_path):
    collect(channel, tmp_path)
    path = run_dir(channel) / "cache" / "videos.json"
    videos = read_json(path)
    for v in videos.values():
        v.pop("thumbnail_url", None)
    path.write_text(__import__("json").dumps(videos, ensure_ascii=False), encoding="utf-8")
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0
    rep = invoke(channel, "report", "--segment", "ru")
    assert rep.exit_code == 0, rep.output
    assert all(v["thumbnail_url"] == "" for v in read_json(run_dir(channel) / "virals.json")["virals"])
    text = (run_dir(channel) / "report.md").read_text(encoding="utf-8")
    assert NO_DATA in text and "[обложка]" not in text
