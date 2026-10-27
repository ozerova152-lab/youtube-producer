"""Независимая проверка критериев T04: повторы, квота и продолжение, неполные данные, ключ.

Написано от критериев приёмки. Сети нет: записанные ответы (кассеты) и подставной HTTP,
который сам считает обращения. Пауза подменена и записывается.
"""

import json
from datetime import timedelta

import httplib2
import pytest
import vcr
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core import collect as collecting
from produce.core import quota, report, runs, youtube
from produce.core.errors import KeyRejectedError, NetworkError, QuotaExceededError
from produce.core.files import read_json
from produce.core.youtube import YouTubeApi

CANARY = "CANARY-T04-VERIFY-77aa-do-not-leak"
RUN = "2026-10_ru_v1"
RU_DOWN = "YouTube не отвечает: 3 попытки подряд."
KEY_MSG = "Ключ не подошёл (YouTube отклонил). Сбор остановлен."


@pytest.fixture(autouse=True)
def world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


@pytest.fixture
def sleeps(monkeypatch):
    log: list[float] = []
    monkeypatch.setattr(youtube, "pause", log.append)
    return log


@pytest.fixture
def env_file(tmp_path):
    p = tmp_path / ".env"
    p.write_text(f"YOUTUBE_API_KEY={CANARY}\n", encoding="utf-8")
    return p


def tape(name):
    return vcr.use_cassette(str(DEMO / "cassettes" / name), record_mode="none",
                            filter_query_parameters=["key", "publishedAfter"])


def cli(channel, env_file, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), "collect", "--segment", "ru",
                                    "--env-file", str(env_file), *args])


def rj(channel):
    return read_json(channel / "runs" / RUN / "run.json")


class Http(httplib2.Http):
    def __init__(self, codes, reason="backendError", ok=None):
        super().__init__()
        self.codes, self.reason, self.ok, self.n = list(codes), reason, ok, 0

    def request(self, uri, method="GET", body=None, headers=None, **kw):
        code = self.codes[min(self.n, len(self.codes) - 1)]
        self.n += 1
        payload = (self.ok if code == 200 else
                   {"error": {"code": code, "message": "m",
                              "errors": [{"message": "m", "reason": self.reason}]}})
        return (httplib2.Response({"status": str(code), "content-type": "application/json"}),
                json.dumps(payload).encode())


def api(http, spent=None):
    return YouTubeApi(CANARY, on_request=(spent.append if spent is not None else None), http=http)


def do_search(a):
    return a.search("q", "RU", "ru", collecting.now())


# ---- критерий 1: 3 повтора, растущая пауза, сообщение, кэш цел ----

def test_c1_exactly_three_retries_growing_pause_message_cache_intact(channel, env_file, sleeps):
    with tape("server_down.yaml") as cas:
        res = cli(channel, env_file, "--confirm")
    assert res.exit_code == 1
    assert RU_DOWN in res.output and "Собранное сохранено" in res.output
    assert CANARY not in res.output and "Traceback" not in res.output
    assert cas.play_count == 1 + 3
    assert sleeps == [1, 2, 4]
    assert sleeps[0] < sleeps[1] < sleeps[2]
    data = rj(channel)  # json валиден, счётчики не засорены неудачами
    assert data["requests_count"] == 0 and data["quota_spent"] == 0
    assert (channel / "runs" / RUN / "run.json").exists()


def test_c1_preexisting_cache_survives_failure(channel, sleeps):
    run = runs.start_run(channel, "2026-10", "ru", "ru").run
    cache = collecting.Cache(run.path / "cache")
    plan = collecting.make_plan(__import__("produce.core.settings", fromlist=["x"])
                                .load_settings(channel),
                                {"id": "ru", "region": "RU", "language": "ru"})
    key = plan.search_key(plan.keywords[0])
    cache.progress["searches"][key] = [{"id": "x1", "channel_id": "c1"}]
    cache.save()
    snapshot = {p.name: p.read_bytes() for p in (run.path / "cache").iterdir()}
    http = Http([503])
    with pytest.raises(NetworkError) as e:
        collecting.collect(run, plan, api(http), cache)
    assert RU_DOWN in str(e.value) and http.n == 4
    after = {p.name: p.read_bytes() for p in (run.path / "cache").iterdir()}
    assert after == snapshot


def test_c1_flaky_then_ok_no_message_pauses_match_failures(sleeps):
    spent: list[int] = []
    http = Http([503, 503, 200], ok={"items": []})
    assert do_search(api(http, spent)) == []
    assert http.n == 3 and sleeps == [1, 2]
    assert spent == [100]  # неудачные попытки квоту не тратят


def test_c1_three_failures_then_ok_still_succeeds_on_third_retry(sleeps):
    http = Http([500, 500, 500, 200], ok={"items": []})
    assert do_search(api(http)) == []
    assert http.n == 4 and sleeps == [1, 2, 4]


def test_c1_four_failures_is_giving_up_not_five_calls(sleeps):
    http = Http([502])
    with pytest.raises(NetworkError):
        do_search(api(http))
    assert http.n == 4 and len(sleeps) == 3


def test_c1_network_exception_is_retried_and_reported_in_russian(sleeps):
    class Dead(httplib2.Http):
        n = 0

        def request(self, *a, **k):
            Dead.n += 1
            raise ConnectionError("reset")

    with pytest.raises(NetworkError) as e:
        do_search(api(Dead()))
    assert Dead.n == 4 and RU_DOWN in str(e.value) and "reset" not in str(e.value)


# ---- критерий 2: квота на половине, продолжение завтра ----

def test_c2_resume_next_day_does_not_repeat_collected(channel, env_file, sleeps):
    with tape("quota_day1.yaml") as c1:
        r1 = cli(channel, env_file, "--confirm")
    assert r1.exit_code == 1
    assert "Квота на сегодня закончилась. Собрано" in r1.output
    assert "Продолжите завтра" in r1.output and "Traceback" not in r1.output
    assert sleeps == []  # квота — не сбой сети: без повторов
    first_requests = [r.uri for r in c1.requests]
    d1 = rj(channel)
    assert 0 < d1["requests_count"] < 10 and d1["quota_spent"] > 0
    searches_day1 = [u for u in first_requests if "/search" in u]
    assert searches_day1  # поиски были собраны в первый день

    # Следующий день: учёт квоты сдвигается, прежние сутки — вчера.
    ledger = channel.parent / "quota.json"
    yday = (quota.quota_day() - timedelta(days=1)).isoformat()
    ledger.write_text(json.dumps({yday: quota.DAILY_LIMIT}), encoding="utf-8")
    with tape("quota_day2.yaml") as c2:
        r2 = cli(channel, env_file, "--confirm")
    assert r2.exit_code == 0, r2.output
    second_requests = [r.uri for r in c2.requests]
    # Что собрано в день 1, во второй день не запрашивается повторно.
    assert not [u for u in second_requests if "/search" in u]
    assert len(set(second_requests)) == len(second_requests)
    assert not set(second_requests) & set(first_requests[:d1["requests_count"]])
    d2 = rj(channel)
    # Число обращений всего = день 1 + день 2; второй день добавил ровно свои.
    assert d2["requests_count"] == d1["requests_count"] + len(second_requests)
    assert d2["stage"] == "собрано"
    day2_spent = read_json(ledger)[quota.quota_day().isoformat()]
    assert day2_spent == sum(c for c in [100 if "/search" in u else 1 for u in second_requests])


def test_c2_same_day_rerun_makes_no_request(channel, env_file, sleeps):
    with tape("quota_day1.yaml"):
        cli(channel, env_file, "--confirm")
    n = rj(channel)["requests_count"]
    with tape("server_down.yaml") as cas:  # любой запрос сломал бы тест счётчиком
        r = cli(channel, env_file, "--confirm")
    assert r.exit_code == 1 and cas.play_count == 0
    assert rj(channel)["requests_count"] == n


def test_c2_quota_error_is_not_retried(sleeps):
    http = Http([403], reason="quotaExceeded")
    with pytest.raises(QuotaExceededError):
        do_search(api(http))
    assert http.n == 1 and sleeps == []


def test_c2_quota_reasons_dailyLimit_also_stops_without_retry(sleeps):
    http = Http([403], reason="dailyLimitExceeded")
    with pytest.raises(QuotaExceededError):
        do_search(api(http))
    assert http.n == 1


# ---- критерий 3: неполные данные в report.md ----

def test_c3_report_md_marks_incomplete_with_count(channel, env_file):
    with tape("collect_ru.yaml"):
        assert cli(channel, env_file, "--confirm").exit_code == 0
    skipped = rj(channel)["incomplete_data"]
    assert len(skipped) >= 1
    res = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert res.exit_code == 0
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert f"Неполные данные: пропущено {len(skipped)} видео" in text


def test_c3_count_matches_for_several_skipped(channel):
    run = runs.start_run(channel, "2026-10", "ru", "ru").run
    (run.path / "cache" / "videos.json").write_text(
        json.dumps({"a": {"id": "a", "views": 1}}), encoding="utf-8")
    runs.set_incomplete(run, ["x1", "x2", "x3"])
    text = report.build_report(runs.load_run(run.path) if hasattr(runs, "load_run") else run)
    assert "пропущено 3 видео" in text


def test_c3_no_skips_no_false_alarm(channel):
    run = runs.start_run(channel, "2026-10", "ru", "ru").run
    (run.path / "cache" / "videos.json").write_text(
        json.dumps({"a": {"id": "a", "views": 1}}), encoding="utf-8")
    text = report.build_report(run)
    assert "пропущено" not in text


# ---- критерий 4: ключ отклонён ----

@pytest.mark.parametrize("reason", ["API_KEY_INVALID", "keyInvalid"])
def test_c4_key_rejected_once_no_retry(reason, sleeps):
    http = Http([400], reason=reason)
    with pytest.raises(KeyRejectedError) as e:
        do_search(api(http))
    assert http.n == 1 and sleeps == []
    assert str(e.value).startswith(KEY_MSG)


def test_c4_cli_message_once_one_request(channel, env_file, sleeps):
    with tape("key_rejected.yaml") as cas:
        res = cli(channel, env_file, "--confirm")
    assert res.exit_code == 1
    assert res.output.count("Ключ не подошёл") == 1
    assert cas.play_count == 1 and sleeps == []
    assert CANARY not in res.output and "Traceback" not in res.output
    assert rj(channel)["requests_count"] <= 1
