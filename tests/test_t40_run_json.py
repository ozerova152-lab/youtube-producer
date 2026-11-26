"""T40: слишком большой version, несовпадение с номером папки и испорченный run.json: понятные сообщения."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app

RUN = "2026-10_ru_v1"
SECRET = "секретное-значение-из-файла"


@pytest.fixture
def channel(tmp_path, monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    path = tmp_path / "chan"
    shutil.copytree(DEMO, path)
    shutil.rmtree(path / "runs", ignore_errors=True)
    settings = path / "settings.yaml"  # свой канал: строка fixed_date только для демо
    settings.write_text("".join(line for line in settings.read_text(encoding="utf-8").splitlines(keepends=True)
                                if not line.startswith("fixed_date:")), encoding="utf-8")
    assert run(path, "start", "--segment", "ru", "--brief-lang", "ru").exit_code == 0
    return path


def run(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args])


def run_json(channel, folder=RUN):
    return channel / "runs" / folder / "run.json"


def set_version(channel, value, folder=RUN):
    path = run_json(channel, folder)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = value
    path.write_text(json.dumps(data), encoding="utf-8")


def rename(channel, new):
    (channel / "runs" / RUN).rename(channel / "runs" / new)
    return new


def no_crash(result):
    for bad in ("Traceback", "TypeError", "ValueError", "KeyError", "JSONDecodeError", "Expecting value"):
        assert bad not in result.output and bad not in repr(result.exception or ""), bad


# --- слишком большой version ----------------------------------------------------------------

@pytest.mark.parametrize("value", [1000, 12345, 10**30])
def test_too_large_version_is_an_error_with_its_own_message(channel, value):
    set_version(channel, value)
    for command in (["later", "--segment", "ru"], ["start", "--segment", "ru", "--brief-lang", "ru"],
                    ["report", "--segment", "ru"]):
        result = run(channel, *command)
        assert result.exit_code == 1, result.output
        assert "поле `version` слишком большое: допустимо целое число от 1 до 999" in result.output
        assert "впишите номер из названия папки (здесь v1, значит 1)" in result.output
        assert str(value) not in result.output  # значение из файла не пересказываем
        no_crash(result)


def test_new_version_folder_with_huge_number_is_never_created(channel):
    set_version(channel, 10**30)
    result = run(channel, "start", "--segment", "ru", "--brief-lang", "ru", "--new-version")
    assert result.exit_code == 1
    assert sorted(p.name for p in (channel / "runs").iterdir()) == [RUN]


def test_version_999_is_allowed_when_the_folder_agrees(channel):
    folder = rename(channel, "2026-10_ru_v999")
    set_version(channel, 999, folder)
    assert run(channel, "later", "--segment", "ru").exit_code == 0


def test_new_version_after_999_preserves_existing_run(channel):
    folder = rename(channel, "2026-10_ru_v999")
    set_version(channel, 999, folder)
    before = run_json(channel, folder).read_bytes()
    result = run(channel, "start", "--segment", "ru", "--brief-lang", "ru", "--new-version")
    assert result.exit_code == 1
    assert "999 версий запуска" in result.output
    assert "Старые запуски не изменены" in result.output
    assert run_json(channel, folder).read_bytes() == before
    assert sorted(p.name for p in (channel / "runs").iterdir()) == [folder]


# --- несовпадение с номером папки ------------------------------------------------------------

@pytest.mark.parametrize("value", [2, 5, 999])
def test_version_not_matching_folder_number_is_an_error(channel, value):
    set_version(channel, value)
    before = run_json(channel).read_bytes()
    result = run(channel, "later", "--segment", "ru")
    assert result.exit_code == 1, result.output
    assert f"`runs/{RUN}/run.json` в поле `version` стоит число, не совпадающее с номером в названии папки (v1)" \
        in result.output
    assert "Впишите 1 и запустите команду снова. Папку не переименовывайте" in result.output
    assert "Старые запуски не изменены" in result.output
    no_crash(result)
    assert run_json(channel).read_bytes() == before


def test_folder_v15_wants_15_and_accepts_15(channel):
    folder = rename(channel, "2026-10_ru_v15")
    set_version(channel, 1, folder)
    result = run(channel, "later", "--segment", "ru")
    assert result.exit_code == 1 and "(v15)" in result.output and "Впишите 15" in result.output
    set_version(channel, 15, folder)
    assert run(channel, "later", "--segment", "ru").exit_code == 0


def test_leading_zero_folder_name_compares_by_number(channel):
    folder = rename(channel, "2026-10_ru_v01")
    set_version(channel, 1, folder)
    assert run(channel, "later", "--segment", "ru").exit_code == 0


# --- пустой, оборванный, не тот run.json -----------------------------------------------------

BROKEN = {
    "empty": b"",
    "spaces": b"   \n  ",
    "truncated": ('{"stage": "настроен", "' + SECRET).encode(),
    "garbage": b"\x00\x01 not json " + SECRET.encode(),
    "bad-bytes": b"\xff\xfe\x00 " + SECRET.encode(),
    "list": b"[1, 2]",
    "number": b"5",
    "string": f'"{SECRET}"'.encode(),
    "null": b"null",
}


@pytest.mark.parametrize("name", BROKEN)
@pytest.mark.parametrize("command", [["later", "--segment", "ru"],
                                     ["start", "--segment", "ru", "--brief-lang", "ru"],
                                     ["report", "--segment", "ru"]])
def test_broken_run_json_gives_plain_message_with_a_way_out(channel, tmp_path, name, command):
    target = run_json(channel)
    target.write_bytes(BROKEN[name])
    result = run(channel, *command)
    assert result.exit_code == 1, result.output
    out = result.output
    assert f"Файл `runs/{RUN}/run.json` пуст или повреждён" in out
    assert "Остальные файлы запуска не тронуты" in out
    assert "если у вас есть копия этого файла, верните её" in out
    assert "переименуйте папку запуска (например, допишите `-old` в конце" in out
    assert "ничего не удалится" in out and "запустите `produce start`" in out
    assert "не тратить квоту заново" in out
    assert str(tmp_path) not in out  # абсолютного пути нет
    assert SECRET not in out  # содержимое файла не пересказываем
    no_crash(result)
    assert target.read_bytes() == BROKEN[name]  # файл не тронут
    assert not list((channel / "runs" / RUN).glob("*.tmp"))


def test_broken_json_message_names_the_place_of_the_error(channel):
    run_json(channel).write_bytes(BROKEN["truncated"])
    result = run(channel, "later", "--segment", "ru")
    assert "ошибка формата в строке 1, столбце" in result.output


def test_missing_run_json_is_the_same_plain_message(channel):
    run_json(channel).unlink()
    result = run(channel, "later", "--segment", "ru")
    assert result.exit_code == 1 and "пуст или повреждён" in result.output
    no_crash(result)


def test_following_the_advice_gives_a_fresh_run_and_keeps_the_old_folder(channel):
    run_json(channel).write_bytes(BROKEN["truncated"])
    (channel / "runs" / RUN / "marker.txt").write_text("кэш", encoding="utf-8")
    rename(channel, RUN + "-old")
    result = run(channel, "start", "--segment", "ru", "--brief-lang", "ru")
    assert result.exit_code == 0, result.output
    assert (channel / "runs" / RUN / "run.json").is_file()
    assert (channel / "runs" / (RUN + "-old") / "marker.txt").read_text(encoding="utf-8") == "кэш"
    assert run_json(channel, RUN + "-old").read_bytes() == BROKEN["truncated"]


def test_broken_run_json_of_a_past_month_does_not_break_later(channel, monkeypatch):
    run_json(channel).write_bytes(BROKEN["empty"])
    monkeypatch.setenv("PRODUCE_NOW", "2026-11-03")  # октябрьский запуск стал прошлым
    result = run(channel, "later", "--segment", "ru")
    assert result.exit_code == 0, result.output
    no_crash(result)


def test_control_good_run_works_as_before(channel):
    result = run(channel, "later", "--segment", "ru")
    assert result.exit_code == 0, result.output
