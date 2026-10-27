"""Независимая проверка критериев T02 (основа скрипта): враждебные случаи.

Команды гоняются настоящим `produce` в подпроцессе: так видно то, что увидит человек.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

from produce.core import quota, runs
from produce.core.errors import FileFormatError, ProduceError, RunError
from produce.core.files import read_json, write_json_atomic

ROOT = Path(__file__).parent.parent
def _run(*a, **k):
    return subprocess.run(*a, check=False, **k)


PRODUCE = Path(sys.executable).parent / "produce"
ALL_STAGES = [
    "настроен", "оценка квоты", "собрано", "залёты", "разбор готов", "ниша готова",
    "стратегия ждёт утверждения", "стратегия утверждена", "брифы на решение", "план готов",
]


def produce(channel, *args, input=None):
    return _run(
        [str(PRODUCE), "--channel", str(channel), *args],
        capture_output=True, text=True, input=input, timeout=60,
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path: Path) -> dict[str, str]:
    return {str(p.relative_to(path)): digest(p) for p in sorted(path.rglob("*")) if p.is_file()}


# --- Критерий 1: сегменты из настроек ---------------------------------------------------------

def add_segment(channel, **seg):
    path = channel / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["segments"].append(seg)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_segments_command_lists_two_then_three(channel):
    before = produce(channel, "segments")
    assert before.returncode == 0
    assert len(before.stdout.strip().splitlines()) == 2
    add_segment(channel, id="de", region="DE", language="de")
    after = produce(channel, "segments")
    lines = after.stdout.strip().splitlines()
    assert len(lines) == 3 and lines[2].startswith("de:") and "DE" in lines[2]


def test_segment_flag_selects_new_segment_and_creates_its_run(channel):
    add_segment(channel, id="de", region="DE", language="de")
    res = produce(channel, "start", "--segment", "de", "--brief-lang", "de", "--month", "2026-11")
    assert res.returncode == 0, res.stdout + res.stderr
    run = read_json(channel / "runs" / "2026-11_de_v1" / "run.json")
    assert run["segment"] == "de" and run["brief_lang"] == "de" and run["stage"] == "настроен"
    assert (channel / "runs" / "2026-11_de_v1" / "cache").is_dir()


def test_unknown_segment_creates_nothing(channel):
    res = produce(channel, "start", "--segment", "zz", "--brief-lang", "ru", "--month", "2026-11")
    assert res.returncode == 1
    assert "zz" in res.stdout and "Traceback" not in res.stdout + res.stderr
    assert not (channel / "runs").exists()


def test_brief_lang_must_be_segment_language_or_russian(channel):
    res = produce(channel, "start", "--segment", "en", "--brief-lang", "fr", "--month", "2026-11")
    assert res.returncode == 1 and "fr" in res.stdout
    assert not (channel / "runs").exists()
    ok = produce(channel, "start", "--segment", "en", "--brief-lang", "ru", "--month", "2026-11")
    assert ok.returncode == 0
    assert read_json(channel / "runs" / "2026-11_en_v1" / "run.json")["brief_lang"] == "ru"


def test_segment_prompt_rejects_garbage_answer(channel):
    res = produce(channel, "start", "--month", "2026-11", input="нет-такого\n\n")
    assert res.returncode == 1 and "нет-такого" in res.stdout
    assert not (channel / "runs").exists()


def test_duplicate_segment_ids_rejected(channel):
    add_segment(channel, id="ru", region="BY", language="ru")
    res = produce(channel, "segments")
    assert res.returncode == 1 and "повторяются" in res.stdout


def test_segment_without_id_rejected_with_filename(channel):
    add_segment(channel, region="DE", language="de")
    res = produce(channel, "segments")
    assert res.returncode == 1 and "settings.yaml" in res.stdout


def test_missing_settings_names_file(tmp_path):
    res = produce(tmp_path / "nochan", "segments")
    assert res.returncode == 1 and "settings.yaml" in res.stdout
    assert not (tmp_path / "nochan").exists()


# --- Критерий 2: v2 после «план готов» -------------------------------------------------------

def test_v2_has_copy_of_cache_and_v1_byte_identical(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    (v1.path / "cache" / "videos.json").write_text('{"id": "x"}', encoding="utf-8")
    (v1.path / "cache" / "sub").mkdir()
    (v1.path / "cache" / "sub" / "c.json").write_text("[1]", encoding="utf-8")
    (v1.path / "virals.json").write_text("[]", encoding="utf-8")
    runs.set_stage(v1, "план готов")
    snapshot = tree(v1.path)
    res = produce(channel, "start", "--segment", "ru", "--brief-lang", "ru", "--month", "2026-11")
    assert res.returncode == 0, res.stdout
    v2 = channel / "runs" / "2026-11_ru_v2"
    assert tree(v1.path) == snapshot
    assert tree(v2 / "cache") == tree(v1.path / "cache")
    # v2 независима: правка кэша v2 не задевает v1
    (v2 / "cache" / "videos.json").write_text("changed", encoding="utf-8")
    assert tree(v1.path) == snapshot
    meta = read_json(v2 / "run.json")
    assert meta["version"] == 2 and meta["stage"] == "настроен"
    assert meta["quota_spent"] == 0 and meta["requests_count"] == 0
    assert not (v2 / "virals.json").exists()


def test_v3_follows_finished_v2_and_v2_unfinished_resumes(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    runs.set_stage(v1, "план готов")
    v2 = runs.start_run(channel, "2026-11", "ru", "ru").run
    again = runs.start_run(channel, "2026-11", "ru", "ru")
    assert again.action == "resume" and again.run.path == v2.path
    assert not (channel / "runs" / "2026-11_ru_v3").exists()
    runs.set_stage(v2, "план готов")
    assert runs.start_run(channel, "2026-11", "ru", "ru").run.path.name == "2026-11_ru_v3"


def test_other_month_and_segment_do_not_trigger_v2(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    runs.set_stage(v1, "план готов")
    assert runs.start_run(channel, "2026-12", "ru", "ru").run.path.name == "2026-12_ru_v1"
    assert runs.start_run(channel, "2026-11", "en", "en").run.path.name == "2026-11_en_v1"


def test_segment_id_with_underscore_and_version_digits_not_confused(channel):
    add_segment(channel, id="ru_v2", region="RU", language="ru")
    runs.start_run(channel, "2026-11", "ru_v2", "ru")
    assert runs.list_runs(channel, "2026-11", "ru") == []
    assert len(runs.list_runs(channel, "2026-11", "ru_v2")) == 1


# --- Критерий 6: остановленный запуск продолжается, v2 не создаётся ---------------------------

@pytest.mark.parametrize("stage", ALL_STAGES[:-1])
def test_every_unfinished_stage_resumes_and_reports_stage(channel, stage):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    runs.set_stage(v1, stage)
    before = tree(v1.path)
    res = produce(channel, "start", "--segment", "ru", "--brief-lang", "ru", "--month", "2026-11")
    assert res.returncode == 0
    assert f"Этап: {stage}" in res.stdout and "Продолжить?" in res.stdout
    assert not (channel / "runs" / "2026-11_ru_v2").exists()
    assert tree(v1.path) == before


def test_new_version_flag_on_unfinished_is_explicit_request(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    runs.set_stage(v1, "собрано")
    res = produce(channel, "start", "--segment", "ru", "--brief-lang", "ru",
                  "--month", "2026-11", "--new-version")
    assert res.returncode == 0
    assert (channel / "runs" / "2026-11_ru_v2" / "run.json").exists()
    assert read_json(v1.path / "run.json")["stage"] == "собрано"


# --- Критерий 3: битые файлы и безопасная запись ---------------------------------------------

BROKEN = {
    "truncated": '{"stage": "настроен", ',
    "empty": "",
    "garbage": "\x00\x01 not json",
    "trailing": '{"stage": "настроен"} xx',
}


@pytest.mark.parametrize("name", BROKEN)
def test_broken_run_json_via_cli_names_file_and_is_untouched(channel, name):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    target = v1.path / "run.json"
    target.write_text(BROKEN[name], encoding="utf-8")
    before = target.read_bytes()
    res = produce(channel, "start", "--segment", "ru", "--brief-lang", "ru", "--month", "2026-11")
    assert res.returncode == 1
    assert "run.json" in res.stdout and "строк" in res.stdout
    assert "Traceback" not in res.stdout + res.stderr
    assert target.read_bytes() == before
    assert [p.name for p in v1.path.iterdir() if p.name.endswith(".tmp")] == []


def test_run_json_wrong_shape_is_human_error(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    (v1.path / "run.json").write_text("[1, 2]", encoding="utf-8")
    res = produce(channel, "start", "--segment", "ru", "--brief-lang", "ru", "--month", "2026-11")
    assert res.returncode == 1 and "run.json" in res.stdout and "Traceback" not in res.stderr


def test_run_json_with_unknown_stage_is_human_error(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    data = read_json(v1.path / "run.json")
    data["stage"] = "что-то"
    (v1.path / "run.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    res = produce(channel, "start", "--segment", "ru", "--brief-lang", "ru", "--month", "2026-11")
    assert res.returncode == 1 and "Неизвестный этап" in res.stdout


def test_json_error_reports_exact_line(tmp_path):
    bad = tmp_path / "videos.json"
    bad.write_text('{\n  "a": 1,\n  "b": ,\n}\n', encoding="utf-8")
    with pytest.raises(FileFormatError) as err:
        read_json(bad)
    assert "videos.json" in str(err.value) and "строке 3" in str(err.value)


def test_missing_file_names_path(tmp_path):
    with pytest.raises(FileFormatError, match="missing.json"):
        read_json(tmp_path / "missing.json")


def test_non_utf8_file_is_format_error(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ProduceError):
        read_json(bad)


def test_invalid_yaml_reports_line_and_file_untouched(channel):
    path = channel / "settings.yaml"
    path.write_text("segments:\n  - id: ru\n   bad: [\n", encoding="utf-8")
    before = path.read_bytes()
    res = produce(channel, "segments")
    assert res.returncode == 1 and "settings.yaml" in res.stdout and "строка" in res.stdout
    assert path.read_bytes() == before


def test_write_goes_through_temp_file_in_same_dir_and_replace(tmp_path, monkeypatch):
    target = tmp_path / "d" / "r.json"
    calls = []
    real = os.replace

    def spy(src, dst):
        calls.append((Path(src), Path(dst)))
        assert Path(src).exists() and Path(src) != Path(dst)
        return real(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    write_json_atomic(target, {"к": "значение"})
    assert len(calls) == 1
    assert calls[0][0].parent == target.parent and calls[0][1] == target
    assert json.loads(target.read_text(encoding="utf-8")) == {"к": "значение"}
    assert [p.name for p in target.parent.iterdir()] == ["r.json"]


def test_unserializable_data_keeps_old_file(tmp_path):
    target = tmp_path / "r.json"
    write_json_atomic(target, {"v": 1})
    with pytest.raises(TypeError):
        write_json_atomic(target, {"v": object()})
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["r.json"]


def test_set_stage_failure_midwrite_keeps_old_run_json(channel, monkeypatch):
    run = runs.start_run(channel, "2026-11", "ru", "ru").run
    before = (run.path / "run.json").read_bytes()

    def boom(src, dst):
        raise OSError("диск полон")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        runs.set_stage(run, "собрано")
    assert (run.path / "run.json").read_bytes() == before


# --- Критерий 4: запрет сети --------------------------------------------------------------------

def test_network_blocked_in_a_fresh_pytest_session_with_project_config(tmp_path):
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import socket, urllib.request\n"
        "def test_socket():\n"
        "    socket.create_connection(('93.184.216.34', 80), timeout=2)\n"
        "def test_http():\n"
        "    urllib.request.urlopen('http://example.com', timeout=2)\n",
        encoding="utf-8",
    )
    res = _run(
        [sys.executable, "-m", "pytest", "-c", str(ROOT / "pyproject.toml"),
         "--rootdir", str(ROOT), str(probe), "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, env={**os.environ, "YOUTUBE_API_KEY": ""}, timeout=120,
    )
    out = res.stdout + res.stderr
    assert res.returncode != 0
    assert "2 failed" in out and "Network is disabled" in out


def test_block_network_is_in_default_pytest_options():
    cfg = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "--block-network" in cfg


# --- Критерий 5: make reset/setup ------------------------------------------------------------

def test_make_reset_idempotent_and_leaves_other_data(tmp_path):
    shutil.copy(ROOT / "Makefile", tmp_path / "Makefile")
    (tmp_path / "data" / "demo" / "runs").mkdir(parents=True)
    (tmp_path / "data" / "demo" / "runs" / "f").write_text("x")
    (tmp_path / "data" / "quota.json").write_text("{}")
    (tmp_path / "examples" / "demo").mkdir(parents=True)
    (tmp_path / "examples" / "demo" / "settings.yaml").write_text("k: 1")
    for _ in range(2):  # повторный сброс на пустом месте не падает
        r = _run(["make", "reset"], cwd=tmp_path, capture_output=True, text=True)
        assert r.returncode == 0
    assert not (tmp_path / "data" / "demo").exists()
    assert (tmp_path / "data" / "quota.json").exists()
    assert (tmp_path / "examples" / "demo" / "settings.yaml").read_text() == "k: 1"


def test_make_setup_recipe_creates_venv_and_installs_project():
    dry = _run(["make", "-n", "setup"], cwd=ROOT, capture_output=True, text=True)
    assert dry.returncode == 0
    assert "venv .venv" in dry.stdout and 'pip install -e ".[dev]"' in dry.stdout


# --- Критерий 7: общий дневной учёт ----------------------------------------------------------

DAY = date(2026, 11, 5)


def test_quota_sums_across_two_channels_and_segments(tmp_path):
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    for d in (a_dir, b_dir):
        d.mkdir()
    ledger = quota.ledger_path(a_dir)
    assert ledger == quota.ledger_path(b_dir)  # общий файл на ключ
    r1 = runs.start_run(a_dir, "2026-11", "ru", "ru").run
    r2 = runs.start_run(b_dir, "2026-11", "en", "en").run
    r3 = runs.start_run(a_dir, "2026-11", "en", "en").run
    runs.record_usage(r1, 1000, 10, ledger, DAY)
    runs.record_usage(r2, 2000, 20, ledger, DAY)
    total = runs.record_usage(r3, 500, 5, ledger, DAY)
    assert total == 3500 == quota.spent_today(ledger, DAY)
    assert [read_json(r.path / "run.json")["quota_spent"] for r in (r1, r2, r3)] == [1000, 2000, 500]


def test_quota_days_are_separate_and_remaining_never_negative(tmp_path):
    ledger = tmp_path / "quota.json"
    quota.add_spent(ledger, 9000, DAY)
    assert quota.spent_today(ledger, date(2026, 11, 6)) == 0
    quota.add_spent(ledger, 5000, DAY)
    assert quota.remaining_today(ledger, DAY) == 0
    assert quota.spent_today(ledger, DAY) == 14000


def test_quota_ledger_survives_between_processes_and_repeat_call_accumulates(tmp_path):
    ledger = tmp_path / "quota.json"
    code = (
        "import sys; from pathlib import Path; from datetime import date;"
        "from produce.core import quota;"
        "print(quota.add_spent(Path(sys.argv[1]), 100, date(2026,11,5)))"
    )
    outs = [_run([sys.executable, "-c", code, str(ledger)], capture_output=True,
                           text=True).stdout.strip() for _ in range(3)]
    assert outs == ["100", "200", "300"]


def test_corrupt_ledger_is_human_error_and_untouched(tmp_path):
    ledger = tmp_path / "quota.json"
    ledger.write_text('{"2026-11-05": 12', encoding="utf-8")
    with pytest.raises(FileFormatError, match="quota.json"):
        quota.add_spent(ledger, 10, DAY)
    assert ledger.read_text(encoding="utf-8") == '{"2026-11-05": 12'


# --- Критерий 8: этапы ------------------------------------------------------------------------

def test_stage_list_matches_spec_exactly_and_in_order():
    assert runs.STAGES == ALL_STAGES


@pytest.mark.parametrize("bad", ["", " ", "План готов", "план готов ", "done", "оценка  квоты",
                                 "собрано;", "залеты"])
def test_near_miss_stage_names_rejected_and_file_unchanged(channel, bad):
    run = runs.start_run(channel, "2026-11", "ru", "ru").run
    before = (run.path / "run.json").read_bytes()
    with pytest.raises(RunError, match="Неизвестный этап"):
        runs.set_stage(run, bad)
    assert (run.path / "run.json").read_bytes() == before
    assert run.data["stage"] == "настроен"


@pytest.mark.parametrize("stage", ALL_STAGES)
def test_each_valid_stage_persisted_to_disk(channel, stage):
    run = runs.start_run(channel, "2026-11", "ru", "ru").run
    runs.set_stage(run, stage)
    assert read_json(run.path / "run.json")["stage"] == stage


def test_run_json_has_all_required_fields(channel):
    run = runs.start_run(channel, "2026-11", "ru", "en").run
    data = read_json(run.path / "run.json")
    assert set(data) >= {"month", "segment", "brief_lang", "version", "stage", "quota_spent",
                         "requests_count", "awaiting_confirmation", "incomplete_data"}
    assert data["awaiting_confirmation"] is False and data["incomplete_data"] == []
    assert data["requests_count"] == 0


# --- Ключ не утекает -------------------------------------------------------------------------

def test_api_key_canary_never_printed_or_saved(channel, tmp_path):
    env = {**os.environ, "YOUTUBE_API_KEY": "CANARY-KEY-777"}
    res = _run(
        [str(PRODUCE), "--channel", str(channel), "start", "--segment", "ru",
         "--brief-lang", "ru", "--month", "2026-11"],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    assert res.returncode == 0
    assert "CANARY" not in res.stdout + res.stderr
    for p in channel.parent.rglob("*"):
        if p.is_file():
            assert "CANARY" not in p.read_text(encoding="utf-8", errors="ignore")
