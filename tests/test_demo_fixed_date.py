"""T32: демо-канал не зависит от сегодняшней даты: `fixed_date` в settings.yaml замораживает «сегодня»."""

import shutil
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.settings import load_settings

LINE = "fixed_date: 2026-10-27\n"


class DecemberDateTime(datetime):
    """Часы компьютера показывают 15 декабря: демо-залёты (22 и 24 октября) уже старше 30 дней."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 12, 15, 12, 0, tzinfo=tz or UTC)


@pytest.fixture
def december(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "")  # «не задана»; после теста значение вернётся к исходному
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr("produce.core.clock.datetime", DecemberDateTime)


@pytest.fixture
def channel(tmp_path):
    path = tmp_path / "demo"
    shutil.copytree(DEMO, path)
    shutil.rmtree(path / "runs", ignore_errors=True)
    return path


def run(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args])


def readme_demo(channel):
    start = run(channel, "start", "--segment", "ru", "--brief-lang", "ru")
    imported = run(channel, "import", str(DEMO / "import_comments.json"), "--segment", "ru")
    virals = run(channel, "virals", "--segment", "ru")
    return start, imported, virals


def test_demo_settings_carry_fixed_date_with_delete_hint():
    text = (DEMO / "settings.yaml").read_text(encoding="utf-8")
    assert LINE in text and "УДАЛИТЕ" in text.split("\n" + LINE)[0]
    assert str(load_settings(DEMO)["fixed_date"]) == "2026-10-27"


def test_readme_demo_gives_same_result_in_december(december, channel):
    start, imported, virals = readme_demo(channel)
    assert start.exit_code == 0, start.output
    assert "Дата зафиксирована для демо: 2026-10-27" in start.output
    assert (channel / "runs" / "2026-10_ru_v1").is_dir()
    assert not list((channel / "runs").glob("2026-12*"))
    assert imported.exit_code == 0 and "Загружено: 11 видео, 2 канала. Обращений к YouTube: 0" in imported.output
    assert virals.exit_code == 0, virals.output
    assert "12.68" in virals.output and "Как использовать нейросеть: выпуск 1" in virals.output


def test_without_fixed_date_the_same_december_breaks_the_demo(december, channel):
    """Контроль: без строки демо ушло бы в декабрьский запуск, значит тест выше реально ловит поломку."""
    settings = channel / "settings.yaml"
    settings.write_text(settings.read_text(encoding="utf-8").replace(LINE, ""), encoding="utf-8")
    start, _, virals = readme_demo(channel)
    assert "Дата зафиксирована" not in start.output
    assert (channel / "runs" / "2026-12_ru_v1").is_dir()
    assert "12.68" not in virals.output


def test_produce_now_beats_fixed_date(monkeypatch, channel):
    monkeypatch.setenv("PRODUCE_NOW", "2026-11-03")
    start = run(channel, "start", "--segment", "ru", "--brief-lang", "ru")
    assert start.exit_code == 0, start.output
    assert (channel / "runs" / "2026-11_ru_v1").is_dir()
    assert "Дата зафиксирована" not in start.output


@pytest.mark.parametrize("value", ["вчера", "2026-13-40", "27.10.2026"])
def test_bad_fixed_date_is_a_human_error(december, channel, value):
    settings = channel / "settings.yaml"
    settings.write_text(settings.read_text(encoding="utf-8").replace(LINE, f"fixed_date: '{value}'\n"),
                        encoding="utf-8")
    result = run(channel, "start", "--segment", "ru", "--brief-lang", "ru")
    assert result.exit_code == 1
    assert "поле `fixed_date` должно быть датой ГГГГ-ММ-ДД" in result.output
    assert "Traceback" not in result.output
    assert not (channel / "runs").exists() or not list((channel / "runs").iterdir())


def test_missing_settings_still_reported_by_the_command_itself(december, tmp_path):
    result = run(tmp_path / "нет-такого", "start", "--segment", "ru")
    assert result.exit_code == 1 and "Не найден файл настроек" in result.output


def test_fixed_date_is_ignored_outside_demo_folder_with_warning(december, tmp_path):
    """Копия настроек демо в другой папке: даты не замораживаются, есть предупреждение на каждой команде."""
    own = tmp_path / "my-channel"
    shutil.copytree(DEMO, own)
    shutil.rmtree(own / "runs", ignore_errors=True)
    segments = run(own)
    assert segments.exit_code == 0
    assert "`fixed_date` игнорируется: это не демо-канал" in segments.output
    start = run(own, "start", "--segment", "ru", "--brief-lang", "ru")
    assert start.exit_code == 0, start.output
    assert "`fixed_date` игнорируется: это не демо-канал" in start.output
    assert "Дата зафиксирована" not in start.output
    assert (own / "runs" / "2026-12_ru_v1").is_dir()  # живые часы, а не 2026-10
    assert not (own / "runs" / "2026-10_ru_v1").exists()


def test_bad_fixed_date_outside_demo_is_only_a_warning(december, tmp_path):
    own = tmp_path / "other"
    shutil.copytree(DEMO, own)
    settings = own / "settings.yaml"
    settings.write_text(settings.read_text(encoding="utf-8").replace(LINE, "fixed_date: 'вчера'\n"),
                        encoding="utf-8")
    result = run(own)
    assert result.exit_code == 0 and "игнорируется: это не демо-канал" in result.output


def test_demo_folder_name_is_checked_after_resolving_the_path(december, tmp_path, monkeypatch):
    """`data/../data/demo` и подобное всё равно демо; папка demo-copy — уже нет."""
    demo = tmp_path / "data" / "demo"
    shutil.copytree(DEMO, demo)
    (tmp_path / "data" / "x").mkdir()
    assert "Дата зафиксирована" in run(demo / ".." / "x" / ".." / "demo", "start", "--segment", "ru",
                                       "--brief-lang", "ru").output
    monkeypatch.setenv("PRODUCE_NOW", "")  # новая команда = новый процесс: дата прошлой не остаётся
    copy = tmp_path / "data" / "demo-copy"
    shutil.copytree(DEMO, copy)
    assert "игнорируется" in run(copy).output
