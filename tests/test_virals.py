"""Поиск залётов: пороги, норма канала, мало данных, ближайшие 5, импорт, сценарии."""

import hashlib
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json, write_json_atomic

RUN = "2026-10_ru_v1"
ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def video(vid, views, likes=None, comments=None, channel="UC1", day=20, live=False):
    return {"id": vid, "title": f"Видео {vid}", "description": "", "channel_id": channel,
            "channel_title": "К", "published_at": f"2026-10-{day:02d}T10:00:00Z",
            "duration_seconds": 600, "is_live": live, "views": views,
            "likes": likes if likes is not None else views // 20,
            "comments": comments if comments is not None else views // 100}


def put_cache(channel, videos):
    cache = channel / "runs" / RUN / "cache"
    cache.mkdir(parents=True)
    write_json_atomic(cache / "videos.json", {v["id"]: v for v in videos})
    write_json_atomic(cache / "channels.json", {})
    write_json_atomic(channel / "runs" / RUN / "run.json", {
        "month": "2026-10", "segment": "ru", "brief_lang": "ru", "version": 1,
        "stage": "собрано", "quota_spent": 0, "requests_count": 0,
        "awaiting_confirmation": False, "incomplete_data": []})


def run_virals(channel):
    result = CliRunner().invoke(app, ["--channel", str(channel), "virals", "--segment", "ru"])
    assert result.exit_code == 0, result.output
    return result, read_json(channel / "runs" / RUN / "virals.json")


def regular(n, views=1000, channel="UC1"):
    return [video(f"{channel}_r{i}", views + i, channel=channel, day=1 + i) for i in range(n)]


def test_thresholds_select_exactly_expected(channel):
    # Каждый кандидат в своём канале с нормой 1004.5, чтобы соседи не влияли на норму.
    vids, ids = [], {"ok": (5000, 200, 20), "low_views": (2500, 100, 10),
                     "low_likes": (5000, 50, 20), "low_comm": (5000, 200, 2)}
    for name, (views, likes, comments) in ids.items():
        vids += regular(10, channel=f"UC_{name}")
        vids.append(video(name, views, likes, comments, channel=f"UC_{name}"))
    put_cache(channel, vids)
    _, data = run_virals(channel)
    assert [v["id"] for v in data["virals"]] == ["ok"]
    v = data["virals"][0]
    assert v["views"] == 5000 and v["norm"] in (1004, 1005)
    assert v["times_norm"] == pytest.approx(5000 / 1004.5, abs=0.01)
    assert v["likes_ratio"] == 0.04 and v["comments_ratio"] == 0.004


def test_boundary_is_inclusive(channel):
    put_cache(channel, regular(10, 1000)[:0] + [video(f"r{i}", 1000, 20, 1, day=1 + i)
                                                for i in range(10)]
              + [video("edge", 3000, 60, 3)])
    _, data = run_virals(channel)
    assert [v["id"] for v in data["virals"]] == ["edge"]


def test_less_than_five_videos_marked_few_data(channel):
    put_cache(channel, regular(3) + [video("big", 90000)])
    result, data = run_virals(channel)
    assert data["virals"] == []
    assert {s["id"] for s in data["skipped"]} == {"big", "UC1_r0", "UC1_r1", "UC1_r2"}
    assert all(s["reason"] == "мало данных" for s in data["skipped"])
    assert "Мало данных" in result.output


def test_norm_uses_10_latest_without_checked_and_live(channel):
    # 12 роликов: 10 обычных, проверяемое и трансляция (с огромными просмотрами)
    old = [video(f"o{i}", 100, day=1) for i in range(3)]  # старше 10 последних: не входят
    last10 = [video(f"n{i}", 1000 + i * 10, day=5 + i) for i in range(10)]
    live = video("live", 999999, channel="UC1", day=26, live=True)
    checked = video("chk", 9000, 400, 40, day=27)
    put_cache(channel, old + last10 + [live, checked])
    _, data = run_virals(channel)
    rec = next(v for v in data["virals"] if v["id"] == "chk")
    assert rec["norm"] == 1045 or rec["norm"] == 1044  # медиана 1000..1090 = 1045
    assert rec["norm_sample"] == 10
    assert "live" not in {v["id"] for v in data["virals"]}


def test_no_virals_shows_five_nearest_and_settings_untouched(channel):
    vids = regular(10)
    near = [video(f"c{i}", 1200 + i * 300, 30, 2, day=21 + i % 5) for i in range(7)]
    put_cache(channel, vids + near)
    settings = channel / "settings.yaml"
    before = hashlib.sha256(settings.read_bytes()).hexdigest()
    result, data = run_virals(channel)
    after = hashlib.sha256(settings.read_bytes()).hexdigest()
    assert before == after
    assert data["virals"] == [] and len(data["nearest"]) == 5
    assert "Залётов нет. Ближайшие 5 к порогу:" in result.output
    assert "менять его вы будете сами" in result.output
    assert data["nearest"][0]["closeness"] >= data["nearest"][-1]["closeness"]


def test_speed_does_not_affect_selection(channel):
    vids = regular(10)
    fast = video("fast", 4000, 100, 10, day=27)   # свежее: скорость выше
    slow = video("slow", 4000, 100, 10, day=12)
    put_cache(channel, vids + [fast, slow])
    _, data = run_virals(channel)
    assert {v["id"] for v in data["virals"]} == {"fast", "slow"}
    by = {v["id"]: v for v in data["virals"]}
    assert by["fast"]["views_per_day"] > by["slow"]["views_per_day"]
    assert by["fast"]["times_norm"] == by["slow"]["times_norm"]


def test_old_videos_are_not_virals(channel):
    old = video("old", 90000, 4000, 400)
    old["published_at"] = "2026-08-01T10:00:00Z"
    put_cache(channel, regular(10) + [old])
    _, data = run_virals(channel)
    assert data["virals"] == []


def test_imported_cache_gives_virals_and_report_section(channel):
    imp = CliRunner().invoke(app, ["--channel", str(channel), "import",
                                   str(DEMO / "import.csv"), "--segment", "ru"])
    assert imp.exit_code == 0, imp.output
    result, data = run_virals(channel)
    assert [v["id"] for v in data["virals"]] == ["demo_v01"]
    assert "Залётов: 1" in result.output
    rep = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert rep.exit_code == 0, rep.output
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert "## Залёты" in text and "demo_v01" in text and "×12.68" in text
    assert read_json(channel / "runs" / RUN / "run.json")["stage"] == "залёты"


def test_no_data_gives_human_error(channel):
    result = CliRunner().invoke(app, ["--channel", str(channel), "virals", "--segment", "ru"])
    assert result.exit_code == 1 and "Traceback" not in result.output


def test_playbooks_cover_flow():
    collect = (ROOT / "playbooks" / "01-collect.md").read_text(encoding="utf-8")
    virals = (ROOT / "playbooks" / "02-virals.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "playbooks/01-collect.md" in claude and "playbooks/02-virals.md" in claude
    assert "produce --channel <канал> collect" in collect.replace(".venv/bin/", "")
    assert "import <файл>" in collect and "сам не ставит" in collect
    assert re.search(r"«ну ок»", collect) and "запусти сбор" in collect
    assert "virals" in virals and "report" in virals and "Залётов нет" in virals
    assert "Мой канал не задан" in virals
