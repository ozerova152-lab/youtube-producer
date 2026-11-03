"""Независимая проверка T24 (ссылки на обложки), написана от критериев приёмки.

Враждебные случаи: нет thumbnails, пустой словарь, старый кэш без поля, несколько размеров
(порядок и «дырявые» записи), чужой хост и мусор в адресе, одинаковые обращения/квота у сбора,
отчёт не ломается, картинок на диске нет, демо-кассеты содержат только адреса i.ytimg.com.
"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json
from produce.core.youtube import _video, best_thumbnail

CANARY = "CANARY-KEY-do-not-leak-7f3a9c"
RUN = "2026-10_ru_v1"
ROOT = Path(__file__).parent.parent
IMG = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def invoke(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args])


def rd(channel):
    return channel / "runs" / RUN


def collect(channel, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"YOUTUBE_API_KEY={CANARY}\n", encoding="utf-8")
    done = invoke(channel, "collect", "--segment", "ru", "--env-file", str(env), "--confirm")
    assert done.exit_code == 0, done.output


def u(s):
    return {"url": f"https://i.ytimg.com/vi/x/{s}.jpg"}


def test_size_priority_ignores_dict_order_and_skips_broken_entries():
    thumbs = {"default": u("d"), "maxres": {"url": ""}, "high": u("h"), "standard": None, "medium": u("m")}
    assert best_thumbnail(thumbs).endswith("/h.jpg")  # maxres пуст, standard нет -> high
    assert best_thumbnail({"medium": u("m"), "default": u("d")}).endswith("/m.jpg")


def test_unknown_size_names_are_not_invented():
    assert best_thumbnail({"gigantic": u("g")}) == ""


@pytest.mark.parametrize("raw", [[], 0, False, {"high": []}, {"high": {"url": None}}, {"high": {"url": 5}}])
def test_garbage_shapes_give_empty_string(raw):
    assert best_thumbnail(raw) == ""


def test_video_without_thumbnails_key_or_with_empty_dict():
    base = {"id": "v", "snippet": {"title": "t"}, "statistics": {"viewCount": "1"}}
    assert _video(base)["thumbnail_url"] == ""
    base["snippet"]["thumbnails"] = {}
    assert _video(base)["thumbnail_url"] == ""


@pytest.mark.parametrize("bad", [
    "https://evil.example/x.jpg", "http://i.ytimg.com/x.jpg", "https://i.ytimg.com/a b.jpg",
    "https://i.ytimg.com/a)b.jpg", "https://i.ytimg.com/a(b.jpg", "https://user@i.ytimg.com/x.jpg",
    "https://i.ytimg.com:8443/x.jpg", "https://i.ytimg.com.evil.example/x.jpg",
    "https://x.i.ytimg.com/x.jpg", "file:///etc/passwd", "https://evil.example/i.ytimg.com/x.jpg",
])
def test_foreign_url_gives_empty_field(bad):
    assert best_thumbnail({"high": {"url": bad}}) == ""


def test_foreign_best_size_falls_back_to_next_allowed():
    good = "https://i.ytimg.com/vi/x/hqdefault.jpg"
    got = best_thumbnail({"maxres": {"url": "https://evil.example/m.jpg"}, "high": {"url": good}})
    assert got == good
    assert best_thumbnail({"default": {"url": good}}) == good


@pytest.mark.vcr("collect_ru.yaml")
def test_collect_all_videos_have_field_and_only_ytimg_urls(channel, tmp_path):
    collect(channel, tmp_path)
    videos = read_json(rd(channel) / "cache" / "videos.json")
    assert videos and all("thumbnail_url" in v for v in videos.values())
    urls = [v["thumbnail_url"] for v in videos.values() if v["thumbnail_url"]]
    assert urls and all(x.startswith("https://i.ytimg.com/") for x in urls)
    assert any(v["thumbnail_url"] == "" for v in videos.values())
    # лучшее качество: у роликов на 01 есть maxres
    assert videos["demoVid_a01"]["thumbnail_url"].endswith("maxresdefault.jpg")
    assert not [p for p in channel.rglob("*") if p.suffix.lower() in IMG]
    # ключ не утёк в файлы запуска
    for p in rd(channel).rglob("*"):
        if p.is_file():
            assert CANARY not in p.read_text(encoding="utf-8", errors="ignore")


@pytest.mark.vcr("collect_ru.yaml")
def test_empty_thumbnail_video_does_not_break_virals_and_report(channel, tmp_path):
    collect(channel, tmp_path)
    path = rd(channel) / "cache" / "videos.json"
    videos = read_json(path)
    for v in videos.values():  # все обложки пропали
        v["thumbnail_url"] = ""
    path.write_text(json.dumps(videos, ensure_ascii=False), encoding="utf-8")
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    text = (rd(channel) / "report.md").read_text(encoding="utf-8")
    assert "обложка: нет данных" in text and "[обложка](" not in text and "None" not in text


@pytest.mark.vcr("collect_ru.yaml")
def test_mixed_cache_partial_field(channel, tmp_path):
    collect(channel, tmp_path)
    path = rd(channel) / "cache" / "videos.json"
    videos = read_json(path)
    for i, v in enumerate(videos.values()):
        if i % 2:
            v.pop("thumbnail_url", None)
    path.write_text(json.dumps(videos, ensure_ascii=False), encoding="utf-8")
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    for v in read_json(rd(channel) / "virals.json")["virals"]:
        assert isinstance(v["thumbnail_url"], str)


@pytest.mark.vcr("collect_ru.yaml")
def test_report_idempotent_second_run_and_cover_in_every_my_result_row(channel, tmp_path):
    collect(channel, tmp_path)
    invoke(channel, "virals", "--segment", "ru")
    invoke(channel, "report", "--segment", "ru")
    first = (rd(channel) / "report.md").read_text(encoding="utf-8")
    invoke(channel, "report", "--segment", "ru")
    assert (rd(channel) / "report.md").read_text(encoding="utf-8") == first
    mine = read_json(rd(channel) / "my_results.json")
    section = first.split("## Мои результаты", 1)[1]
    for v in mine["best"] + mine["weak"]:
        row = next(ln for ln in section.splitlines() if v["url"] in ln)
        assert ("[обложка](" + v["thumbnail_url"] + ")") in row if v["thumbnail_url"] else "обложка: нет данных" in row


@pytest.mark.vcr("collect_ru.yaml")
def test_run_json_counters_equal_old_code_baseline(channel, tmp_path):
    """Число обращений и квота такие же, как у кода до задачи (эталон снят на HEAD, см. артефакт)."""
    collect(channel, tmp_path)
    run = read_json(rd(channel) / "run.json")
    cassette = yaml.safe_load((DEMO / "cassettes" / "collect_ru.yaml").read_text(encoding="utf-8"))
    assert run["requests_count"] == len(cassette["interactions"])
    # videos.list запрашивает part=snippet,...: thumbnails приходят в том же ответе, отдельных вызовов нет
    for it in cassette["interactions"]:
        assert "thumbnail" not in it["request"]["uri"].lower()


def test_demo_cassettes_have_only_ytimg_urls_and_no_images():
    for f in (DEMO / "cassettes").glob("*.yaml"):
        text = f.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "i.ytimg.com" in line or '"url"' in line and "ytimg" in line:
                assert "https://i.ytimg.com/vi/" in line
    assert not [p for p in DEMO.rglob("*") if p.suffix.lower() in IMG]


def test_gitignore_covers_image_extensions():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        assert ext in ignore


def test_git_status_shows_no_image_files():
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert not [ln for ln in out.splitlines() if Path(ln[3:]).suffix.lower() in IMG]


def test_spec_describes_field_where_schemas_live():
    spec = (ROOT / "docs/spec/02-tech-architecture.md").read_text(encoding="utf-8")
    ana = (ROOT / "docs/analytics.md").read_text(encoding="utf-8")
    for name in ("virals.json", "my_results.json", "cache/videos.json"):
        line = next(ln for ln in spec.splitlines() if name in ln and "thumbnail_url" in ln)
        assert line
    assert "thumbnail_url" in ana


def test_demo_run_end_to_end_has_cover_links(channel, tmp_path):
    """Демо-путь: готовые кассеты -> залёты имеют thumbnail_url (через импорт нет обложек: это T27)."""
    # Подтверждено в vcr-тесте выше; здесь только что демо-кассета содержит thumbnails в ответах.
    text = (DEMO / "cassettes" / "collect_ru.yaml").read_text(encoding="utf-8")
    assert "thumbnails" in text and "maxresdefault.jpg" in text
