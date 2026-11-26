"""T38: нечисловой `version` в run.json не роняет команды трейсбеком, а объясняется простыми словами."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app

RUN = "2026-10_ru_v1"
BAD = ['"abc"', "null", "[1]", "1.5", "true", "0", "-1", '"2"', "{}", "MISSING"]


@pytest.fixture
def channel(tmp_path, monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    path = tmp_path / "chan"
    shutil.copytree(DEMO, path)
    shutil.rmtree(path / "runs", ignore_errors=True)
    # fixed_date остаётся только демо: свой канал её не содержит
    settings = path / "settings.yaml"
    settings.write_text("".join(line for line in settings.read_text(encoding="utf-8").splitlines(keepends=True)
                                if not line.startswith("fixed_date:")), encoding="utf-8")
    result = CliRunner().invoke(app, ["--channel", str(path), "start", "--segment", "ru", "--brief-lang", "ru"])
    assert result.exit_code == 0, result.output
    return path


def set_version(channel, raw):
    path = channel / "runs" / RUN / "run.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if raw == "MISSING":
        data.pop("version")
    else:
        data["version"] = json.loads(raw)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args])


def assert_human_error(result):
    out = result.output
    assert result.exit_code == 1, out
    assert "поле `version` должно быть целым числом, например 1" in out
    assert f"`runs/{RUN}/run.json`" in out
    assert "впишите номер из названия папки (здесь v1, значит 1)" in out
    assert "Старые запуски не изменены" in out
    for bad in ("Traceback", "TypeError", "ValueError", "KeyError", "invalid literal"):
        assert bad not in out and bad not in repr(result.exception or ""), bad


@pytest.mark.parametrize("raw", BAD)
def test_later_says_what_is_wrong_in_plain_words(channel, raw):
    set_version(channel, raw)
    assert_human_error(run(channel, "later", "--segment", "ru"))


@pytest.mark.parametrize("command", [["start", "--segment", "ru", "--brief-lang", "ru"],
                                     ["report", "--segment", "ru"], ["virals", "--segment", "ru"]])
@pytest.mark.parametrize("raw", ['"abc"', "null", '"2"'])
def test_every_command_reading_the_run_is_covered(channel, command, raw):
    set_version(channel, raw)
    assert_human_error(run(channel, *command))


def test_error_does_not_copy_the_value_and_leaves_the_file_unchanged(channel):
    path = set_version(channel, '"секретное значение"')
    before = path.read_bytes()
    result = run(channel, "later", "--segment", "ru")
    assert_human_error(result)
    assert "секретное значение" not in result.output
    assert path.read_bytes() == before


def test_control_good_version_still_works(channel):
    result = run(channel, "later", "--segment", "ru")
    assert result.exit_code == 0, result.output
    assert "Прошлых запуска нет" in result.output or "Прошлых запусков нет" in result.output


def test_broken_version_in_a_past_month_does_not_break_later(channel, monkeypatch):
    """Версию прошлых запусков берут из имени папки: битый run.json старого месяца команду не роняет."""
    set_version(channel, '"abc"')
    monkeypatch.setenv("PRODUCE_NOW", "2026-11-03")  # октябрьский запуск стал прошлым
    result = run(channel, "later", "--segment", "ru")
    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output
