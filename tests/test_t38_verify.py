"""T38 (независимая проверка): битый `version` в run.json через НАСТОЯЩИЙ бинарник `.venv/bin/produce`.

Подпроцесс, а не CliRunner: так видны реальные stdout/stderr/код выхода и настоящий трейсбек, если он есть.
Каждая команда, читающая запуск, получает все виды битого значения; файлы запуска не меняются.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import DEMO

ROOT = Path(__file__).parent.parent
BIN = ROOT / ".venv" / "bin" / "produce"
SPEC = ROOT / "docs" / "spec" / "04-user-flows.md"
RUN = "2026-10_ru_v1"
# ключеподобные строки собираются в рантайме: gitleaks не должен видеть их ни в исходнике, ни в .pyc
SECRET = "AI" + "za" + "SyA1234567890abcdefghijklmnopqrstuv".upper().lower()
LONG = "Ж" * 5000
BAD = ['"abc"', "null", "[1]", "1.5", "true", "false", "0", "-1", '"2"', '"1"', "{}", "1e3", "MISSING",
       json.dumps("<script>alert(1)</script>"), json.dumps(SECRET), json.dumps(LONG)]
LEAKS = ("<script>", SECRET[:6], "ЖЖЖЖЖ", "alert(1)")
FORBIDDEN = ("Traceback", "TypeError", "ValueError", "KeyError", "JSONDecodeError", "invalid literal")

pytestmark = pytest.mark.skipif(not BIN.exists(), reason="нет .venv/bin/produce (make setup-dev)")


def _env(month="2026-10-27"):
    env = dict(os.environ, PRODUCE_NOW=month)
    env.pop("YOUTUBE_API_KEY", None)
    return env


def produce(chan: Path, *args, now="2026-10-27"):
    return subprocess.run([str(BIN), "--channel", str(chan), *args], capture_output=True, text=True,
                          env=_env(now), cwd=chan.parent, input="", timeout=120, check=False)


@pytest.fixture
def chan(tmp_path) -> Path:
    path = tmp_path / "chan"
    shutil.copytree(DEMO, path)
    shutil.rmtree(path / "runs", ignore_errors=True)
    settings = path / "settings.yaml"  # fixed_date действует только в папке demo
    settings.write_text("".join(x for x in settings.read_text(encoding="utf-8").splitlines(keepends=True)
                                if not x.startswith("fixed_date:")), encoding="utf-8")
    (tmp_path / "fake.env").write_text("YOUTUBE_API_KEY=" + "AI" + "za" + "FAKE" * 8 + "000".lower() + "\n")
    done = produce(path, "start", "--segment", "ru", "--brief-lang", "ru")
    assert done.returncode == 0, done.stdout + done.stderr
    return path


def write_version(chan: Path, raw: str, run=RUN) -> Path:
    path = chan / "runs" / run / "run.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if raw == "MISSING":
        data.pop("version")
    else:
        data["version"] = json.loads(raw)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def expected_message(folder=RUN, number="1", shown="1"):
    return (f"В файле `runs/{folder}/run.json` поле `version` должно быть целым числом, например 1. "
            f"Скорее всего, файл правили руками. Откройте его, впишите номер из названия папки "
            f"(здесь v{number}, значит {shown}) и запустите команду снова. Старые запуски не изменены")


COMMANDS = {
    "later": ["later", "--segment", "ru"],
    "start": ["start", "--segment", "ru", "--brief-lang", "ru"],
    "start-new-version": ["start", "--segment", "ru", "--brief-lang", "ru", "--new-version"],
    "import": ["import", str(DEMO / "import.csv"), "--segment", "ru"],
    "virals": ["virals", "--segment", "ru"],
    "report": ["report", "--segment", "ru"],
    "overview": ["overview", "--segment", "ru"],
    "check-files": ["check-files", "--segment", "ru"],
    "check-covers": ["check-files", "--step", "covers", "--segment", "ru"],
    "check-strategy": ["check-files", "--step", "strategy", "--segment", "ru"],
    "check-briefs": ["check-files", "--step", "briefs", "--segment", "ru"],
    "check-plan": ["check-files", "--step", "plan", "--segment", "ru"],
    "comments": ["comments", "--segment", "ru"],
    "comments-confirm": ["comments", "--segment", "ru", "--confirm"],
    "collect-estimate": ["collect", "--segment", "ru", "--env-file", "FAKE_ENV"],  # без --confirm: сети нет
}


@pytest.mark.parametrize("raw", BAD)
@pytest.mark.parametrize("name", COMMANDS)
def test_every_run_reading_command_explains_bad_version(chan, name, raw):
    write_version(chan, raw)
    before = snapshot(chan)
    args = [str(chan.parent / "fake.env") if a == "FAKE_ENV" else a for a in COMMANDS[name]]
    result = produce(chan, *args)
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert expected_message() in " ".join(out.split()), out
    for word in FORBIDDEN + LEAKS:
        assert word not in out, word
    assert snapshot(chan) == before, "команда с битым version не должна ничего менять"


@pytest.mark.parametrize("content", ["", "[1, 2]", "null", "42", "{"])
@pytest.mark.parametrize("name", ["later", "start", "report", "overview", "virals", "check-files"])
def test_unreadable_run_json_is_not_a_traceback(chan, name, content):
    """Не про version: сообщение может быть другим, но трейсбека и правки файлов быть не должно."""
    (chan / "runs" / RUN / "run.json").write_text(content, encoding="utf-8")
    before = snapshot(chan)
    result = produce(chan, *COMMANDS[name])
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert "run.json" in out
    for word in FORBIDDEN:
        assert word not in out, out
    assert snapshot(chan) == before


@pytest.mark.parametrize("version", [1, 2, 15])
def test_good_version_works_as_before(chan, version):
    if version != 1:
        old, new = chan / "runs" / RUN, chan / "runs" / f"2026-10_ru_v{version}"
        old.rename(new)
        data = json.loads((new / "run.json").read_text(encoding="utf-8"))
        data["version"] = version
        (new / "run.json").write_text(json.dumps(data), encoding="utf-8")
    later = produce(chan, "later", "--segment", "ru")
    assert later.returncode == 0, later.stdout + later.stderr
    start = produce(chan, "start", "--segment", "ru", "--brief-lang", "ru")
    assert f"Запуск 2026-10, ru, v{version}. Этап: настроен. Продолжить?" in start.stdout
    imported = produce(chan, *COMMANDS["import"])
    assert imported.returncode == 0, imported.stdout + imported.stderr
    report = produce(chan, "report", "--segment", "ru")
    assert report.returncode == 0, report.stdout + report.stderr


def test_number_in_message_comes_from_folder_name(chan):
    old, new = chan / "runs" / RUN, chan / "runs" / "2026-10_ru_v15"
    old.rename(new)
    write_version(chan, '"abc"', run="2026-10_ru_v15")
    out = produce(chan, "later", "--segment", "ru").stdout
    assert expected_message("2026-10_ru_v15", "15", "15") in " ".join(out.split())


def test_zero_padded_folder_number(chan):
    (chan / "runs" / RUN).rename(chan / "runs" / "2026-10_ru_v01")
    write_version(chan, "null", run="2026-10_ru_v01")
    out = produce(chan, "later", "--segment", "ru").stdout
    assert expected_message("2026-10_ru_v01", "01", "1") in " ".join(out.split())


@pytest.mark.parametrize("raw", ['"abc"', "null", "MISSING", "-1"])
def test_broken_version_in_past_month_does_not_break_later(chan, raw):
    """Прошлый месяц с битым run.json; версия там берётся из имени папки. Текущий запуск (ноябрь) нормальный."""
    write_version(chan, raw)
    now = "2026-11-03"
    started = produce(chan, "start", "--segment", "ru", "--brief-lang", "ru", now=now)
    assert started.returncode == 0, started.stdout + started.stderr
    later = produce(chan, "later", "--segment", "ru", now=now)
    out = later.stdout + later.stderr
    assert later.returncode == 0, out
    for word in FORBIDDEN:
        assert word not in out
    assert "поле `version`" not in out


def test_past_month_broken_and_no_current_run_still_ok(chan):
    write_version(chan, '"abc"')
    later = produce(chan, "later", "--segment", "ru", now="2026-11-03")
    assert later.returncode == 0, later.stdout + later.stderr
    assert "Traceback" not in later.stdout + later.stderr


def test_non_standard_folder_name_message_has_no_number_hint(tmp_path):
    """Недостижимо через CLI (list_runs берёт только папки по шаблону), поэтому через load_run напрямую."""
    folder = tmp_path / "my-run"
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"stage": "настроен", "version": "x"}), encoding="utf-8")
    code = ("import sys; from pathlib import Path; from produce.core import runs\n"
            "try: runs.load_run(Path(sys.argv[1]))\n"
            "except runs.RunError as e: print(e)\n")
    out = subprocess.run([str(ROOT / ".venv/bin/python"), "-I", "-c", code, str(folder)],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert "поле `version` должно быть целым числом, например 1" in out
    assert "runs/my-run/run.json" in out
    assert "впишите целое число и запустите" in out
    assert "здесь v" not in out
    assert "«x»" not in out and "'x'" not in out  # значение не копируется


def test_spec_text_matches_real_message(chan):
    spec = SPEC.read_text(encoding="utf-8")
    found = re.search(r"«(В файле `runs/<папка запуска>/run\.json`.*?Старые запуски не изменены)»", spec, re.DOTALL)
    assert found, "в потоке 5 нет текста сообщения"
    template = found[1].replace("<папка запуска>", RUN).replace("здесь v1, значит 1", "здесь v1, значит 1")
    write_version(chan, "null")
    out = produce(chan, "later", "--segment", "ru").stdout
    assert template in " ".join(out.split())
    # и подстановка номера: в спеке «здесь v1, значит 1» дан как пример для v1
    assert "номер подставляется из названия папки" in spec
