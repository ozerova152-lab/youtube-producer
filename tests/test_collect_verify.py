"""Независимая проверка критериев T03: оценка квоты, подтверждение, кэш, ключ, кассеты.

Тесты написаны от критериев приёмки, а не от кода: сбор прогоняется на подставном
клиенте YouTube (считает обращения сам) и на записанных ответах. Сети нет.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import produce.cli as cli_module
from conftest import DEMO
from produce.cli import app
from produce.core import collect as collecting
from produce.core import quota, runs
from produce.core.errors import NetworkError
from produce.core.files import read_json

CANARY = "CANARY-VERIFY-9c1e5b-do-not-leak"
RUN = "2026-10_ru_v1"
ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(f"YOUTUBE_API_KEY={CANARY}\n", encoding="utf-8")
    return path


def collect(channel, env_file, *args, segment="ru"):
    return CliRunner().invoke(app, ["--channel", str(channel), "collect", "--segment", segment,
                                    "--env-file", str(env_file), *args])


def run_json(channel):
    return read_json(channel / "runs" / RUN / "run.json")


def edit_settings(channel, **changes):
    path = channel / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def total_of(output):
    return int(output.split("~")[1].split(" из")[0].replace(" ", ""))


# ---------- подставной YouTube: считает обращения независимо от программы ----------

class FakeApi:
    """Минимальный двойник YouTubeApi. Все числа — наши, не из кода программы."""

    def __init__(self, fail_on_search=None):
        self.calls = []
        self.fail_on_search = fail_on_search
        self.searches_done = 0

    # у каждого автора по 30 роликов, свежий мир на 2026-10-27
    def search(self, query, region, language, published_after):
        self.calls.append(("search", query))
        if self.fail_on_search is not None and self.searches_done == self.fail_on_search:
            raise NetworkError("сбой")
        self.searches_done += 1
        n = len(self.calls)
        return [{"id": f"v{query}{i}", "channel_id": f"UC{query}"} for i in range(2)] + [
            {"id": f"shared{n % 1}", "channel_id": "UCshared"}]

    def videos(self, ids):
        self.calls.append(("videos", tuple(ids)))
        return [self._video(i) for i in ids]

    def _video(self, vid):
        return {"id": vid, "title": vid, "description": "", "channel_id": "x",
                "channel_title": "x", "published_at": "2026-10-20T00:00:00Z",
                "duration_seconds": 600, "is_live": False, "views": 100, "likes": 1,
                "comments": 1}

    def channels(self, ids):
        self.calls.append(("channels", tuple(ids)))
        return [{"id": c, "title": c, "subscribers": 10, "video_count": 30,
                 "uploads_playlist": "UU" + c} for c in ids]

    def uploads(self, playlist_id, limit):
        self.calls.append(("uploads", playlist_id, limit))
        today = datetime(2026, 10, 27, tzinfo=UTC)
        out = [{"id": f"{playlist_id}-r{i}",
                "published_at": (today - timedelta(days=5 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")}
               for i in range(limit)]
        return out

    def count(self, kind):
        return sum(1 for c in self.calls if c[0] == kind)


def core_collect(channel, api, competitors=()):
    settings = yaml.safe_load((channel / "settings.yaml").read_text(encoding="utf-8"))
    settings["competitors"] = list(competitors)
    seg = settings["segments"][0]
    plan = collecting.make_plan(settings, seg)
    started = runs.start_run(channel, "2026-10", "ru", "ru")
    run = started.run
    cache = collecting.Cache(run.path / "cache")
    ledger = quota.ledger_path(channel)
    costs = {"search": 100}

    class Counting:
        def __getattr__(self, name):
            fn = getattr(api, name)

            def wrapper(*a, **k):
                result = fn(*a, **k)
                runs.record_usage(run, costs.get(name, 1), 1, ledger)
                return result
            return wrapper

    summary = collecting.collect(run, plan, Counting(), cache,
                                 moment=datetime(2026, 10, 27, tzinfo=UTC))
    return run, cache, summary


# ---------- критерий 1: оценка без --confirm, затем сбор ----------

def test_estimate_has_all_three_parts_and_zero_requests(channel, env_file):
    result = collect(channel, env_file)
    assert result.exit_code == 0, result.output
    out = result.output
    # поиск (3 слова сегмента ru) и верхняя оценка на комментарии названы в сводке
    assert "3 поиска" in out and "до 20 на комментарии залётов" in out
    # оценка не меньше 3 поисков по 100 + 20 на комментарии + хотя бы по запросу списков
    assert total_of(out) > 320
    data = run_json(channel)
    assert data["awaiting_confirmation"] is True
    assert (data["requests_count"], data["quota_spent"]) == (0, 0)
    assert not (channel.parent / "quota.json").exists()


def test_estimate_grows_with_competitors(channel, env_file):
    base = total_of(collect(channel, env_file).output)
    edit_settings(channel, competitors=["UC_a", "UC_b"])
    assert total_of(collect(channel, env_file).output) > base


def test_estimate_for_other_segment_uses_its_words(channel, env_file):
    edit_settings(channel, keywords={"ru": ["a"], "en": ["x", "y", "z", "w", "v"]})
    out = collect(channel, env_file, segment="en").output
    assert "5 поисков" in out
    assert "1 поиск" in collect(channel, env_file, segment="ru").output


def test_estimate_run_files_are_per_segment(channel, env_file):
    collect(channel, env_file, segment="ru")
    collect(channel, env_file, segment="en")
    names = sorted(p.name for p in (channel / "runs").iterdir())
    assert names == ["2026-10_en_v1", "2026-10_ru_v1"]


def test_unknown_segment_and_missing_segment_are_human_errors(channel, env_file):
    bad = collect(channel, env_file, segment="zz")
    assert bad.exit_code == 1 and "zz" in bad.output and "Traceback" not in bad.output
    none = CliRunner().invoke(app, ["--channel", str(channel), "collect",
                                    "--env-file", str(env_file)])
    assert none.exit_code == 1 and "--segment" in none.output


def test_segment_without_keywords_is_human_error(channel, env_file):
    edit_settings(channel, keywords={"ru": [], "en": ["x"]})
    result = collect(channel, env_file)
    assert result.exit_code == 1 and "Traceback" not in result.output
    assert "keywords" in result.output


# ---------- критерий 2: нет ключа ----------

@pytest.mark.parametrize("content", [None, "", "YOUTUBE_API_KEY=\n", "YOUTUBE_API_KEY=   \n",
                                     "YOUTUBE_API_KEY=''\n", "# YOUTUBE_API_KEY=abc\n",
                                     "OTHER=1\n"])
@pytest.mark.parametrize("flags", [[], ["--confirm"]])
def test_missing_or_blank_key(channel, tmp_path, content, flags):
    env = tmp_path / "e.env"
    if content is not None:
        env.write_text(content, encoding="utf-8")
    result = collect(channel, env, *flags)
    assert result.exit_code == 1
    assert "Ключа YouTube нет" in result.output
    assert "README" in result.output and "CSV/JSON" in result.output
    assert "Traceback" not in result.output
    # ни запусков, ни записей учёта: обращений ровно 0
    assert not (channel / "runs").exists() and not (channel.parent / "quota.json").exists()


# ---------- критерий 3: канарейка ----------

@pytest.mark.vcr("key_rejected.yaml")
def test_canary_absent_when_key_rejected(channel, env_file, caplog):
    caplog.set_level(logging.DEBUG)
    result = collect(channel, env_file, "--confirm")
    assert result.exit_code == 1
    blob = result.output + "\n".join(r.getMessage() for r in caplog.records
                                     if not r.name.startswith("vcr"))
    for path in channel.parent.rglob("*"):
        if path.is_file() and path != env_file:
            blob += path.read_text(encoding="utf-8", errors="replace")
    assert CANARY not in blob


def test_canary_absent_after_estimate_and_in_stderr(channel, env_file):
    result = collect(channel, env_file)
    blob = result.output
    for path in channel.parent.rglob("*"):
        if path.is_file() and path != env_file:
            blob += path.read_text(encoding="utf-8", errors="replace")
    assert CANARY not in blob


def test_canary_not_in_repo_cassettes_or_sources():
    for base in (DEMO, ROOT / "src", ROOT / "scripts"):
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".yaml", ".json", ".py", ".md"}:
                assert CANARY not in path.read_text(encoding="utf-8")
    for path in (DEMO / "cassettes").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert "key=" not in text and "AIza" not in text


# ---------- критерий 4: устаревшие кассеты, make check ----------

def run_cassette_check(directory):
    return subprocess.run([sys.executable, "-m", "produce.core.cassettes", str(directory)],
                          check=False, capture_output=True, text=True, cwd=ROOT)


def test_stale_cassette_warning_via_real_command(tmp_path):
    (tmp_path / "old.yaml").write_text("interactions: []\n", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"old.yaml": {"recorded_at": "2025-01-01"}}), encoding="utf-8")
    done = run_cassette_check(tmp_path)
    assert done.returncode == 0  # предупреждение, не поломка
    assert "ПРЕДУПРЕЖДЕНИЕ" in done.stdout and "old.yaml" in done.stdout
    assert "6 месяцев" in done.stdout


def test_fresh_cassettes_no_warning_and_boundary(tmp_path):
    fresh = (datetime.now() - timedelta(days=150)).date().isoformat()
    edge = (datetime.now() - timedelta(days=200)).date().isoformat()
    (tmp_path / "fresh.yaml").write_text("interactions: []\n", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"fresh.yaml": {"recorded_at": fresh}}), encoding="utf-8")
    ok = run_cassette_check(tmp_path)
    assert "ПРЕДУПРЕЖДЕНИЕ" not in ok.stdout and ok.returncode == 0
    (tmp_path / "manifest.json").write_text(
        json.dumps({"fresh.yaml": {"recorded_at": edge}}), encoding="utf-8")
    assert "ПРЕДУПРЕЖДЕНИЕ" in run_cassette_check(tmp_path).stdout


def test_broken_manifest_does_not_crash_silently(tmp_path):
    (tmp_path / "a.yaml").write_text("interactions: []\n", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"a.yaml": {"recorded_at": "не дата"}}), encoding="utf-8")
    done = run_cassette_check(tmp_path)
    assert "ПРЕДУПРЕЖДЕНИЕ" in done.stdout and "Traceback" not in done.stderr


def test_make_check_runs_cassette_step():
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    check_line = next(ln for ln in text.splitlines() if ln.startswith("check:"))
    assert "cassettes" in check_line
    assert "produce.core.cassettes" in text


# ---------- критерии 5-7: сбор по плану, на подставном YouTube ----------

def test_empty_competitors_only_keyword_search(channel):
    api = FakeApi()
    run, cache, summary = core_collect(channel, api)
    assert api.count("search") == 3  # ровно слова сегмента
    assert (run.path / "cache" / "videos.json").exists()
    assert (run.path / "cache" / "channels.json").exists()
    assert summary.videos > 0 and summary.channels > 0
    assert not any(c.get("competitor") for c in cache.channels.values())


def test_competitors_recent_videos_in_window_and_authors_up_to_20(channel):
    api = FakeApi()
    _run, cache, _ = core_collect(channel, api, competitors=["UCcomp"])
    comp = cache.channels["UCcomp"]
    assert comp["competitor"] is True
    # подставной канал выдаёт ролики каждые 5 дней: за 30 дней это 0..6, дальше нельзя
    ids = comp["recent_ids"]
    assert ids and len(ids) == 7
    assert all(i in cache.videos for i in ids)
    # у автора из поиска запрошено ровно до 20 последних и они все в кэше
    author = next(c for k, c in cache.channels.items() if k.startswith("UC") and k != "UCcomp"
                  and not c.get("competitor"))
    assert len(author["recent_ids"]) == 20 and all(i in cache.videos for i in author["recent_ids"])
    limits = {c[1]: c[2] for c in api.calls if c[0] == "uploads"}
    assert limits[author["uploads_playlist"]] == 20
    # последние ролики берутся списком загрузок, а не поиском: поисков осталось только 3
    assert api.count("search") == 3


def test_quota_units_match_independent_count(channel):
    api = FakeApi()
    run, _, summary = core_collect(channel, api)
    expected = 100 * api.count("search") + sum(
        1 for c in api.calls if c[0] != "search")
    assert run.data["quota_spent"] == expected == summary.quota_spent
    assert run.data["requests_count"] == len(api.calls) == summary.requests
    ledger = json.loads((channel.parent / "quota.json").read_text(encoding="utf-8"))
    assert sum(ledger.values()) == expected


# ---------- критерий 8: report ----------

def test_report_section_matches_cache_numbers(channel, env_file):
    api = FakeApi()
    run, cache, _ = core_collect(channel, api)
    result = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert result.exit_code == 0, result.output
    text = (run.path / "report.md").read_text(encoding="utf-8")
    assert "## Собрано" in text
    assert f"Видео: {len(cache.videos)}" in text and f"Каналов: {len(cache.channels)}" in text
    assert f"Квоты потрачено: {run.data['quota_spent']} ед." in text


def test_report_without_run_or_without_data_is_human(channel):
    first = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert first.exit_code == 1 and "Traceback" not in first.output
    assert not list(channel.rglob("report.md"))


# ---------- критерий 9: повтор ----------

def test_repeat_collect_zero_new_requests(channel):
    api = FakeApi()
    core_collect_run = core_collect(channel, api, competitors=["UCcomp"])
    first_calls = len(api.calls)
    # второй проход по тому же запуску
    run = runs.list_runs(channel, "2026-10", "ru")[-1]
    settings = yaml.safe_load((channel / "settings.yaml").read_text(encoding="utf-8"))
    settings["competitors"] = ["UCcomp"]
    plan = collecting.make_plan(settings, settings["segments"][0])
    cache = collecting.Cache(run.path / "cache")
    assert collecting.estimate(plan, cache).searches == 0
    api2 = FakeApi()
    collecting.collect(run, plan, api2, cache, moment=datetime(2026, 10, 27, tzinfo=UTC))
    assert api2.calls == [] and first_calls > 0 and core_collect_run


def test_interrupted_collect_resumes_without_respending(channel):
    broken = FakeApi(fail_on_search=1)  # первый поиск проходит, второй падает
    with pytest.raises(NetworkError):
        core_collect(channel, broken)
    run = runs.list_runs(channel, "2026-10", "ru")[-1]
    progress = read_json(run.path / "cache" / "progress.json")
    assert len(progress["searches"]) == 1  # прогресс цел
    settings = yaml.safe_load((channel / "settings.yaml").read_text(encoding="utf-8"))
    plan = collecting.make_plan(settings, settings["segments"][0])
    cache = collecting.Cache(run.path / "cache")
    assert collecting.estimate(plan, cache).searches == 2
    healthy = FakeApi()
    collecting.collect(run, plan, healthy, cache, moment=datetime(2026, 10, 27, tzinfo=UTC))
    assert healthy.count("search") == 2  # первый поиск повторно не покупался


# ---------- критерий 10: отказ ключа ----------

@pytest.mark.vcr("key_rejected.yaml")
def test_rejected_key_message_exact_and_state_intact(channel, env_file):
    result = collect(channel, env_file, "--confirm")
    assert result.exit_code == 1
    assert ("Ключ не подошёл (YouTube отклонил). Сбор остановлен. "
            "Проверьте ключ в `.env` или загрузите файл") in result.output
    assert "Traceback" not in result.output and CANARY not in result.output
    assert run_json(channel)["awaiting_confirmation"] is False
    # после отказа файлы читаются и повторная оценка работает (прогресс цел)
    again = collect(channel, env_file)
    assert again.exit_code == 0 and "Запускаем сбор?" in again.output


def test_nonempty_key_estimate_makes_no_network_call(channel, env_file, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("клиент YouTube создан на оценке")
    monkeypatch.setattr(cli_module, "YouTubeApi", boom)
    result = collect(channel, env_file)
    assert result.exit_code == 0, result.output
    assert run_json(channel)["requests_count"] == 0


# ---------- критерий 11: не хватает квоты ----------

def keywords_for(n):
    return {"ru": [f"слово{i}" for i in range(n)], "en": ["x"]}


def estimate_for(channel, env_file, n):
    edit_settings(channel, keywords=keywords_for(n))
    return total_of(collect(channel, env_file).output)


def test_9800_estimate_with_600_spent_is_blocked_with_facts(channel, env_file):
    # подбираем число слов, при котором оценка около 9 800
    n = 1
    while estimate_for(channel, env_file, n) < 9800:
        n += 1
    est = estimate_for(channel, env_file, n)
    assert 9800 <= est < 10_000
    (channel.parent / "quota.json").write_text(
        json.dumps({quota.quota_day().isoformat(): 600}), encoding="utf-8")
    for flags in ([], ["--confirm"]):
        before = run_json(channel)
        result = collect(channel, env_file, *flags)
        assert result.exit_code == 1, result.output
        need = f"{est:,}".replace(",", " ")
        assert f"Нужно ~{need}, доступно 9 400. Продолжим завтра, прогресс сохранится" in result.output
        assert run_json(channel)["requests_count"] == before["requests_count"] == 0
    assert not (channel / "runs" / RUN / "cache" / "videos.json").exists()


def test_quota_boundary_exact_fit_passes_one_short_blocks(channel, env_file):
    edit_settings(channel, keywords=keywords_for(10))
    est = total_of(collect(channel, env_file).output)
    ledger = channel.parent / "quota.json"
    day = quota.quota_day().isoformat()
    ledger.write_text(json.dumps({day: 10_000 - est}), encoding="utf-8")
    assert collect(channel, env_file).exit_code == 0  # ровно хватает
    ledger.write_text(json.dumps({day: 10_000 - est + 1}), encoding="utf-8")
    result = collect(channel, env_file)
    assert result.exit_code == 1 and "Продолжим завтра" in result.output


def test_spent_yesterday_does_not_count_today(channel, env_file):
    (channel.parent / "quota.json").write_text(
        json.dumps({"2000-01-01": 10_000}), encoding="utf-8")
    assert collect(channel, env_file).exit_code == 0


def test_corrupt_ledger_is_human_or_safe(channel, env_file):
    (channel.parent / "quota.json").write_text("{не json", encoding="utf-8")
    result = collect(channel, env_file)
    # человеческое сообщение или безопасная работа, но не необработанное исключение
    assert result.exception is None or isinstance(result.exception, SystemExit), repr(result.exception)


# ---------- критерий 12: «нет» ----------

def test_no_answer_leaves_pending_with_zero_requests(channel, env_file):
    collect(channel, env_file)
    for _ in range(3):  # человек молчит или отказывается: состояние не меняется
        data = run_json(channel)
        assert data["awaiting_confirmation"] is True and data["requests_count"] == 0
        collect(channel, env_file)
    assert run_json(channel)["quota_spent"] == 0


# ---------- служебное ----------

def test_no_real_network_in_this_module():
    assert "--block-network" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert os.environ.get("YOUTUBE_API_KEY") is None
