"""Сбор данных YouTube на кассетах: оценка квоты, подтверждение, кэш, ключ."""

import json
import logging
from datetime import date

import pytest
import yaml
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core import cassettes
from produce.core.files import read_json

CANARY = "CANARY-KEY-do-not-leak-7f3a9c"
RUN = "2026-10_ru_v1"


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    # Кассеты записаны на 2026-10-27: «сегодня» фиксируем, чтобы окно 30 дней не уезжало.
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(f"YOUTUBE_API_KEY={CANARY}\n", encoding="utf-8")
    return path


def collect(channel, env_file, *args):
    return CliRunner().invoke(
        app, ["--channel", str(channel), "collect", "--segment", "ru",
              "--env-file", str(env_file), *args])


def run_json(channel):
    return read_json(channel / "runs" / RUN / "run.json")


def cache(channel, name):
    return read_json(channel / "runs" / RUN / "cache" / name)


def set_competitors(channel, competitors):
    path = channel / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["competitors"] = competitors
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_estimate_only_does_not_touch_network(channel, env_file):
    # Нет кассеты и сеть закрыта: любое обращение к YouTube упало бы.
    result = collect(channel, env_file)
    assert result.exit_code == 0, result.output
    assert "Расход: ~" in result.output and "из 10 000 единиц" in result.output
    assert "3 поиска" in result.output and "Запускаем сбор?" in result.output
    data = run_json(channel)
    assert data["awaiting_confirmation"] is True
    assert data["requests_count"] == 0 and data["quota_spent"] == 0
    assert data["stage"] == "оценка квоты"
    assert not (channel / "runs" / RUN / "cache" / "videos.json").exists()
    # «Нет» на оценке — это то же состояние: повторный вызов ничего не меняет.
    assert collect(channel, env_file).exit_code == 0
    assert run_json(channel)["requests_count"] == 0


def test_estimate_includes_comment_upper_bound(channel, env_file):
    out = collect(channel, env_file).output
    # 3 поиска = 300, плюс запросы списков и 20 на комментарии залётов.
    total = int(out.split("~")[1].split(" из")[0].replace(" ", ""))
    assert total >= 300 + 20
    assert "до 20 на комментарии залётов" in out


def test_no_key_gives_instruction_and_no_requests(channel, tmp_path):
    result = collect(channel, tmp_path / "нет-такого.env", "--confirm")
    assert result.exit_code == 1
    assert "Ключа YouTube нет" in result.output
    assert "README" in result.output and "CSV/JSON" in result.output
    assert "Traceback" not in result.output
    assert not (channel / "runs").exists()


def test_empty_key_is_same_as_no_key(channel, tmp_path):
    empty = tmp_path / ".env"
    empty.write_text("YOUTUBE_API_KEY=\n", encoding="utf-8")
    result = collect(channel, empty)
    assert result.exit_code == 1 and "Ключа YouTube нет" in result.output


@pytest.mark.vcr("collect_ru.yaml")
def test_collect_with_empty_competitors_and_canary(channel, env_file, caplog):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("googleapiclient").setLevel(logging.DEBUG)
    result = collect(channel, env_file, "--confirm")
    assert result.exit_code == 0, result.output
    assert "Собираю: поиск 2 из 3" in result.output
    assert "Собрано:" in result.output and "Неполные данные:" in result.output
    videos, channels = cache(channel, "videos.json"), cache(channel, "channels.json")
    assert videos and channels
    assert not any(c.get("competitor") for c in channels.values())
    data = run_json(channel)
    assert data["stage"] == "собрано" and data["awaiting_confirmation"] is False
    assert data["requests_count"] == 10
    report = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert report.exit_code == 0, report.output

    # Записи vcr — это журнал самого тестового инструмента, не программы.
    own = [r.getMessage() for r in caplog.records if not r.name.startswith("vcr")]
    assert any("URL being requested" in line for line in own)  # клиент Google пишет, но без ключа
    everything = result.output + "\n".join(own)
    for path in (channel / "runs" / RUN).rglob("*"):
        if path.is_file():
            everything += path.read_text(encoding="utf-8")
    assert CANARY not in everything


@pytest.mark.vcr("collect_ru.yaml")
def test_author_recent_uploads_cached(channel, env_file):
    collect(channel, env_file, "--confirm")
    videos, channels = cache(channel, "videos.json"), cache(channel, "channels.json")
    # У автора с 6 роликами в кэше все 6, в том числе старше 30 дней.
    a = channels["UC_demo_a"]
    assert len(a["recent_ids"]) == 6 and all(i in videos for i in a["recent_ids"])
    assert "demoVid_a06" in videos
    assert all(len(c["recent_ids"]) <= 20 for c in channels.values())
    # Трансляция помечена, чтобы норма канала её не брала.
    assert videos["demoVid_d04"]["is_live"] is True and videos["demoVid_a01"]["is_live"] is False
    # Скрытые подписчики не превращаются в ноль.
    assert channels["UC_demo_c"]["subscribers"] is None
    # Закрытое видео не вернулось из videos.list: помечено как неполные данные.
    assert "demoVid_b99" in run_json(channel)["incomplete_data"]
    assert "demoVid_b99" not in videos


@pytest.mark.vcr("collect_ru_competitors.yaml")
def test_competitor_videos_in_window_cached(channel, env_file):
    set_competitors(channel, ["UC_demo_comp"])
    result = collect(channel, env_file, "--confirm")
    assert result.exit_code == 0, result.output
    videos, channels = cache(channel, "videos.json"), cache(channel, "channels.json")
    assert channels["UC_demo_comp"]["competitor"] is True
    # Два ролика за 30 дней есть, сентябрьский (старше окна) в кэш не идёт.
    assert {"demoVid_e01", "demoVid_e02"} <= set(videos)
    assert "demoVid_e03" not in videos


@pytest.mark.vcr("collect_ru.yaml")
def test_repeat_collect_spends_nothing(channel, env_file):
    collect(channel, env_file, "--confirm")
    before = run_json(channel)
    ledger = json.loads((channel.parent / "quota.json").read_text(encoding="utf-8"))
    again = collect(channel, env_file, "--confirm")
    assert again.exit_code == 0, again.output
    after = run_json(channel)
    assert (after["requests_count"], after["quota_spent"]) == (
        before["requests_count"], before["quota_spent"])
    assert json.loads((channel.parent / "quota.json").read_text(encoding="utf-8")) == ledger
    # Оценка по готовому кэшу показывает только резерв на комментарии.
    estimate = collect(channel, env_file).output
    assert "~20 из" in estimate and "0 поисков" in estimate


@pytest.mark.vcr("collect_ru.yaml")
def test_report_has_collected_section(channel, env_file):
    collect(channel, env_file, "--confirm")
    spent = run_json(channel)["quota_spent"]
    result = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert result.exit_code == 0
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    videos = len(cache(channel, "videos.json"))
    channels = len(cache(channel, "channels.json"))
    assert "## Собрано" in text
    assert f"- Видео: {videos}" in text and f"- Каналов: {channels}" in text
    assert f"- Квоты потрачено: {spent} ед." in text


def test_report_without_data_is_human_message(channel, env_file):
    collect(channel, env_file)
    result = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert result.exit_code == 1 and "сначала `produce collect`" in result.output


@pytest.mark.vcr("key_rejected.yaml")
def test_rejected_key_stops_with_message_and_keeps_state(channel, env_file):
    result = collect(channel, env_file, "--confirm")
    assert result.exit_code == 1
    assert ("Ключ не подошёл (YouTube отклонил). Сбор остановлен. "
            "Проверьте ключ в `.env` или загрузите файл") in result.output
    assert CANARY not in result.output and "Traceback" not in result.output
    data = run_json(channel)  # run.json цел и читается
    assert data["quota_spent"] == 0 and data["stage"] == "оценка квоты"


def test_rejected_key_not_discovered_on_estimate(channel, env_file):
    # Без --confirm сети нет вовсе (она закрыта в тестах): ключ не проверяется.
    result = collect(channel, env_file)
    assert result.exit_code == 0 and run_json(channel)["requests_count"] == 0


def test_not_enough_quota_blocks_even_with_confirm(channel, env_file):
    day = cassettes_day()
    (channel.parent / "quota.json").write_text(json.dumps({day: 9900}), encoding="utf-8")
    for extra in ([], ["--confirm"]):
        result = collect(channel, env_file, *extra)
        assert result.exit_code == 1, result.output
        assert "доступно 100. Продолжим завтра, прогресс сохранится" in result.output
        assert "Нужно ~" in result.output
    assert run_json(channel)["requests_count"] == 0
    assert run_json(channel)["awaiting_confirmation"] is False


def cassettes_day():
    from produce.core import quota
    return quota.quota_day().isoformat()


def test_stale_cassette_warning(tmp_path):
    (tmp_path / "old.yaml").write_text("interactions: []\n", encoding="utf-8")
    (tmp_path / "new.yaml").write_text("interactions: []\n", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "old.yaml": {"recorded_at": "2026-01-01"},
        "new.yaml": {"recorded_at": "2026-09-01"},
    }), encoding="utf-8")
    found = cassettes.stale_cassettes(tmp_path, today=date(2026, 10, 27))
    assert len(found) == 1 and "old.yaml" in found[0] and "6 месяцев" in found[0]
    # Без даты записи кассета тоже сигналит.
    (tmp_path / "nodate.yaml").write_text("interactions: []\n", encoding="utf-8")
    assert any("nodate.yaml" in w for w in cassettes.stale_cassettes(tmp_path, date(2026, 10, 27)))


def test_demo_cassettes_have_dates_and_no_keys():
    assert cassettes.stale_cassettes(DEMO / "cassettes", today=date(2026, 10, 27)) == []
    for path in (DEMO / "cassettes").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert "key=" not in text and "AIza" not in text and "fake-key" not in text
