"""Сбои YouTube и квота: повторы, продолжение завтра, пометка неполных данных.

Кассеты `server_down`, `quota_day1`, `quota_day2` собраны вручную по формату
официальных ответов (scripts/make_demo_cassettes.py). Пауза между повторами подменена.
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
from produce.core import quota, runs, youtube
from produce.core.errors import KeyRejectedError, NetworkError, QuotaExceededError
from produce.core.files import read_json
from produce.core.youtube import YouTubeApi

CANARY = "CANARY-KEY-do-not-leak-4d2b81"
RUN = "2026-10_ru_v1"
DOWN = ("YouTube не отвечает: 3 попытки подряд. Собранное сохранено. "
        "Запустите позже, повторно квота не потратится; «да» понадобится снова")


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


@pytest.fixture
def pauses(monkeypatch):
    """Вместо сна запоминаем, сколько секунд программа собиралась ждать."""
    waited: list[float] = []
    monkeypatch.setattr(youtube, "pause", waited.append)
    return waited


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(f"YOUTUBE_API_KEY={CANARY}\n", encoding="utf-8")
    return path


def cassette(name):
    return vcr.use_cassette(
        str(DEMO / "cassettes" / name), record_mode="none",
        filter_query_parameters=["key", "publishedAfter"])


def collect(channel, env_file, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), "collect", "--segment", "ru",
                                    "--env-file", str(env_file), *args])


def run_json(channel):
    return read_json(channel / "runs" / RUN / "run.json")


def ledger(channel):
    return channel.parent / "quota.json"


class ScriptedHttp(httplib2.Http):
    """Отвечает по списку кодов, остаток списка повторяет последний код."""

    def __init__(self, statuses, body=None):
        super().__init__()
        self.statuses, self.body, self.calls = list(statuses), body, 0

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        code = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        payload = self.body(code) if self.body else _error(code)
        return (httplib2.Response({"status": str(code), "content-type": "application/json"}),
                json.dumps(payload).encode())


def _error(code, reason="backendError", message="boom"):
    return {"error": {"code": code, "message": message,
                      "errors": [{"message": message, "reason": reason}]}}


def api_for(http, spent=None):
    return YouTubeApi(CANARY, on_request=(spent.append if spent is not None else None), http=http)


def search(api):
    return api.search("q", "RU", "ru", collecting.now())


# ---------- повторы ----------

def test_three_retries_with_growing_pause_then_message_and_intact_cache(channel, env_file, pauses):
    with cassette("server_down.yaml") as cas:
        result = collect(channel, env_file, "--confirm")
    assert result.exit_code == 1
    assert DOWN in result.output
    assert "Traceback" not in result.output and CANARY not in result.output
    assert cas.play_count == 4  # первая попытка и ровно 3 повтора
    assert pauses == [1, 2, 4] and pauses == sorted(set(pauses))
    data = run_json(channel)  # run.json цел и читается; сбои квоту не тратят
    assert data["quota_spent"] == 0 and data["requests_count"] == 0
    assert data["awaiting_confirmation"] is False
    assert not ledger(channel).exists()


def test_failure_in_the_middle_keeps_earlier_cache(channel, pauses):
    run = runs.start_run(channel, "2026-10", "ru", "ru").run
    cache = collecting.Cache(run.path / "cache")
    plan = collecting.make_plan(
        read_settings(channel), {"id": "ru", "region": "RU", "language": "ru"})
    first = plan.search_key(plan.keywords[0])
    cache.progress["searches"][first] = [{"id": "demoVid_a01", "channel_id": "UC_demo_a"}]
    cache.save()
    before = (run.path / "cache" / "progress.json").read_text(encoding="utf-8")

    http = ScriptedHttp([503])
    with pytest.raises(NetworkError) as err:
        collecting.collect(run, plan, api_for(http), cache)
    assert str(err.value) == DOWN
    assert http.calls == 4 and pauses == [1, 2, 4]
    # Уже собранный поиск лежит на диске как был, повторить его не придётся.
    assert (run.path / "cache" / "progress.json").read_text(encoding="utf-8") == before
    again = collecting.Cache(run.path / "cache")
    assert first in again.progress["searches"]


def test_recovery_after_two_failures(pauses):
    spent: list[int] = []
    http = ScriptedHttp([503, 500, 200], body=lambda c: _error(c) if c != 200 else {"items": []})
    assert search(api_for(http, spent)) == []
    assert http.calls == 3 and pauses == [1, 2]
    assert spent == [100]  # потрачено только на удавшийся запрос


@pytest.mark.parametrize("code", [500, 503, 429])
def test_server_errors_are_retried(code, pauses):
    http = ScriptedHttp([code])
    with pytest.raises(NetworkError):
        search(api_for(http))
    assert http.calls == 4


def test_connection_failure_is_retried(pauses):
    class Dead(httplib2.Http):
        calls = 0

        def request(self, *a, **kw):
            Dead.calls += 1
            raise OSError("connection reset")

    with pytest.raises(NetworkError) as err:
        search(api_for(Dead()))
    assert Dead.calls == 4 and str(err.value) == DOWN


def test_other_client_errors_not_retried(pauses):
    http = ScriptedHttp([404], body=lambda c: _error(c, "notFound"))
    with pytest.raises(NetworkError):
        search(api_for(http))
    assert http.calls == 1 and pauses == []


# ---------- ключ ----------

def test_rejected_key_one_request_no_retries_no_pause(pauses):
    body = _error(400, "API_KEY_INVALID", "API key not valid. Please pass a valid API key.")
    http = ScriptedHttp([400], body=lambda c: body)
    with pytest.raises(KeyRejectedError) as err:
        search(api_for(http))
    assert http.calls == 1 and pauses == []
    assert str(err.value) == ("Ключ не подошёл (YouTube отклонил). Сбор остановлен. "
                              "Проверьте ключ в `.env` или загрузите файл")


def test_rejected_key_via_cli_cassette_one_request(channel, env_file, pauses):
    with cassette("key_rejected.yaml") as cas:
        result = collect(channel, env_file, "--confirm")
    assert result.exit_code == 1 and "Ключ не подошёл (YouTube отклонил)" in result.output
    assert cas.play_count == 1 and pauses == []


# ---------- квота кончилась и продолжение завтра ----------

def test_quota_exhausted_halfway_then_resume_next_day(channel, env_file, pauses):
    with cassette("quota_day1.yaml") as cas:
        first = collect(channel, env_file, "--confirm")
    assert first.exit_code == 1, first.output
    assert "Квота на сегодня закончилась. Собрано " in first.output
    assert "%, прогресс сохранён. Продолжите завтра" in first.output
    assert "Traceback" not in first.output and pauses == []  # квота не повторяется
    assert cas.play_count == 6  # 5 удачных запросов и один отказ
    day1 = run_json(channel)
    assert day1["requests_count"] == 5 and day1["quota_spent"] == 302
    assert day1["stage"] == "оценка квоты"
    assert (channel / "runs" / RUN / "cache" / "videos.json").exists()

    # В тот же день сбор больше не стучится: сутки помечены потраченными.
    today = quota.quota_day().isoformat()
    assert read_json(ledger(channel))[today] == quota.DAILY_LIMIT
    again = collect(channel, env_file, "--confirm")
    assert again.exit_code == 1 and "Продолжим завтра" in again.output
    assert run_json(channel)["requests_count"] == 5

    # Наступает следующий день.
    yesterday = (quota.quota_day() - timedelta(days=1)).isoformat()
    ledger(channel).write_text(json.dumps({yesterday: quota.DAILY_LIMIT}), encoding="utf-8")
    estimate = collect(channel, env_file).output
    assert "3 поиска" not in estimate and "0 поисков" in estimate

    with cassette("quota_day2.yaml") as cas2:
        second = collect(channel, env_file, "--confirm")
    assert second.exit_code == 0, second.output
    assert cas2.play_count == 5  # только то, чего не хватало: поиски не повторялись
    data = run_json(channel)
    assert data["requests_count"] == 10 and data["quota_spent"] == 307  # как в сборе за один день
    assert data["stage"] == "собрано"
    spent_day2 = read_json(ledger(channel))[quota.quota_day().isoformat()]
    assert spent_day2 == 5  # новые сутки: 4 списка загрузок и ролики, без уже собранного


# ---------- неполные данные в отчёте ----------

def test_report_marks_incomplete_data_with_count(channel, env_file):
    with cassette("collect_ru.yaml"):
        assert collect(channel, env_file, "--confirm").exit_code == 0
    skipped = run_json(channel)["incomplete_data"]
    assert skipped == ["demoVid_b99"]
    result = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert result.exit_code == 0
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert "## Неполные данные" in text
    assert "Неполные данные: пропущено 1 видео" in text and "demoVid_b99" in text


def test_report_has_no_incomplete_section_when_nothing_skipped(channel):
    run = runs.start_run(channel, "2026-10", "ru", "ru").run
    (run.path / "cache" / "videos.json").write_text(
        json.dumps({"v1": {"id": "v1", "views": 5}}), encoding="utf-8")
    from produce.core import report
    text = report.build_report(run)
    assert "- Неполные данные: 0 видео" in text and "## Неполные данные" not in text


def test_interruption_still_records_skipped_videos(channel, pauses):
    run = runs.start_run(channel, "2026-10", "ru", "ru").run
    cache = collecting.Cache(run.path / "cache")
    cache.progress["unavailable_videos"] = ["gone1", "gone2"]
    plan = collecting.Plan("ru", "RU", "ru", ["x"], [])
    http = ScriptedHttp([403], body=lambda c: _error(c, "quotaExceeded", "quota"))
    with pytest.raises(QuotaExceededError):
        collecting.collect(run, plan, api_for(http), cache)
    assert read_json(run.path / "run.json")["incomplete_data"] == ["gone1", "gone2"]


def read_settings(channel):
    from produce.core.settings import load_settings
    return load_settings(channel)
