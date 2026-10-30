import json
import socket
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from produce.cli import app
from produce.core import quota, runs
from produce.core.errors import FileFormatError, RunError
from produce.core.files import read_json, write_json_atomic
from produce.core.settings import load_api_key

ROOT = Path(__file__).parent.parent


def invoke(channel, *args, input=None):
    return CliRunner().invoke(app, ["--channel", str(channel), *args], input=input)


def test_third_segment_added_by_record_only(channel):
    path = channel / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["segments"].append({"id": "de", "region": "DE", "language": "de"})
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    result = invoke(channel, "segments")
    assert result.exit_code == 0
    assert [line.split(":")[0] for line in result.output.splitlines()] == ["ru", "en", "de"]
    flagged = invoke(channel, "start", "--segment", "de", "--brief-lang", "ru", "--month", "2026-11")
    assert "ещё нет запуска" in flagged.output
    assert (channel / "runs" / "2026-11_de_v1" / "run.json").exists()


def test_start_without_flags_asks(channel):
    result = invoke(channel, "start", "--month", "2026-11", input="en\n\n")
    assert result.exit_code == 0
    assert "Какой берём?" in result.output
    run = read_json(channel / "runs" / "2026-11_en_v1" / "run.json")
    assert run["segment"] == "en" and run["brief_lang"] == "en"


def test_unknown_segment_is_human_error(channel):
    result = invoke(channel, "start", "--segment", "xx", "--brief-lang", "ru")
    assert result.exit_code == 1
    assert "Сегмента «xx» нет в настройках" in result.output


def test_v2_copies_cache_after_plan_ready_and_keeps_v1(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    (v1.path / "cache" / "videos.json").write_text('{"a": 1}', encoding="utf-8")
    runs.set_stage(v1, "план готов")
    result = runs.start_run(channel, "2026-11", "ru", "ru", force_new_version=True)
    assert result.action == "new_version"
    assert result.run.path.name == "2026-11_ru_v2"
    assert (result.run.path / "cache" / "videos.json").read_text(encoding="utf-8") == '{"a": 1}'
    assert (v1.path / "cache" / "videos.json").exists()
    assert read_json(v1.path / "run.json")["stage"] == "план готов"
    assert result.run.data["quota_spent"] == 0


def test_unfinished_run_is_resumed_not_v2(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    runs.set_stage(v1, "стратегия ждёт утверждения")
    result = invoke(channel, "start", "--segment", "ru", "--brief-lang", "ru", "--month", "2026-11")
    assert "Этап: стратегия ждёт утверждения. Продолжить?" in result.output
    assert not (channel / "runs" / "2026-11_ru_v2").exists()
    # прямая просьба разрешает v2
    forced = runs.start_run(channel, "2026-11", "ru", "ru", force_new_version=True)
    assert forced.run.path.name == "2026-11_ru_v2"


def test_segments_do_not_mix(channel):
    runs.start_run(channel, "2026-11", "ru", "ru")
    assert runs.start_run(channel, "2026-11", "en", "en").action == "created"


def test_broken_json_message_and_file_untouched(tmp_path):
    bad = tmp_path / "run.json"
    bad.write_text('{"stage": "настроен", ', encoding="utf-8")
    with pytest.raises(FileFormatError) as err:
        read_json(bad)
    assert str(bad) in str(err.value) and "строке 1" in str(err.value)
    assert bad.read_text(encoding="utf-8") == '{"stage": "настроен", '


def test_broken_settings_message(channel):
    (channel / "settings.yaml").write_text("segments: [\n  - id: ru\n", encoding="utf-8")
    result = invoke(channel, "segments")
    assert result.exit_code == 1
    assert "settings.yaml" in result.output and "строка" in result.output


def test_atomic_write_failure_keeps_old_file(tmp_path, monkeypatch):
    target = tmp_path / "x.json"
    write_json_atomic(target, {"v": 1})

    def boom(src, dst):
        raise OSError("disk")

    monkeypatch.setattr("produce.core.files.os.replace", boom)
    with pytest.raises(OSError):
        write_json_atomic(target, {"v": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_network_is_blocked():
    with pytest.raises(RuntimeError, match="Network is disabled"):
        socket.create_connection(("example.com", 80), timeout=2)


def test_daily_quota_sums_across_runs(channel):
    ledger = quota.ledger_path(channel)
    a = runs.start_run(channel, "2026-11", "ru", "ru").run
    b = runs.start_run(channel, "2026-11", "en", "en").run
    runs.record_usage(a, 600, 6, ledger)
    total = runs.record_usage(b, 9200, 40, ledger)
    assert total == 9800
    assert quota.spent_today(ledger) == 9800
    assert quota.remaining_today(ledger) == 200
    assert read_json(b.path / "run.json")["quota_spent"] == 9200
    assert read_json(a.path / "run.json")["requests_count"] == 6


def test_unknown_stage_is_error(channel):
    run = runs.start_run(channel, "2026-11", "ru", "ru").run
    with pytest.raises(RunError, match="Неизвестный этап"):
        runs.set_stage(run, "почти готово")
    assert read_json(run.path / "run.json")["stage"] == "настроен"


def test_all_ten_stages_accepted(channel):
    run = runs.start_run(channel, "2026-11", "ru", "ru").run
    for stage in runs.STAGES:
        runs.set_stage(run, stage)
    assert len(runs.STAGES) == 10


def test_api_key_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert load_api_key(tmp_path / ".env") is None
    env = tmp_path / ".env"
    env.write_text("YOUTUBE_API_KEY=\n", encoding="utf-8")
    assert load_api_key(env) is None
    env.write_text("YOUTUBE_API_KEY='canary-123'\n", encoding="utf-8")
    assert load_api_key(env) == "canary-123"


def test_make_reset_removes_demo_data_keeps_examples(tmp_path):
    (tmp_path / "Makefile").write_text((ROOT / "Makefile").read_text(encoding="utf-8"))
    (tmp_path / "data" / "demo").mkdir(parents=True)
    (tmp_path / "data" / "mine").mkdir()
    (tmp_path / "examples" / "demo").mkdir(parents=True)
    subprocess.run(["make", "reset"], cwd=tmp_path, check=True, capture_output=True)
    assert not (tmp_path / "data" / "demo").exists()
    assert (tmp_path / "data" / "mine").exists()
    assert (tmp_path / "examples" / "demo").exists()


def test_make_setup_upgrades_pip_before_installing_dependencies():
    """Свежий pip нужен каждому, кто клонирует проект: пакетам его даёт старый Python."""
    steps = subprocess.run(
        ["make", "-n", "setup"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    upgrade = next(i for i, s in enumerate(steps) if "pip install -U pip" in s)
    install = next(i for i, s in enumerate(steps) if "pip install -e" in s)
    assert upgrade < install


def test_make_setup_for_user_does_not_download_chromium():
    """T21: новичок по быстрому старту не качает браузер (около 120 МБ нужен только проверке витрины)."""
    steps = subprocess.run(
        ["make", "-n", "setup"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    assert "playwright" not in steps and "chromium" not in steps.lower()


def test_make_setup_dev_adds_dev_extras_and_chromium():
    """T21: полный набор разработчика остался: dev-зависимости и Chromium для `make check`."""
    steps = subprocess.run(
        ["make", "-n", "setup-dev"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    assert 'pip install -e ".[dev]"' in steps
    assert "playwright install chromium" in steps


def test_make_audit_runs_pip_audit_and_is_not_part_of_check():
    """Аудит ходит в сеть и со временем краснеет сам: `make check` остаётся без него."""
    audit = subprocess.run(
        ["make", "-n", "audit"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    assert "pip-audit" in audit
    check = subprocess.run(
        ["make", "-n", "check"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    assert "pip-audit" not in check
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dev = pyproject.split("[project.optional-dependencies]")[1].split("]")[0]
    assert "pip-audit" in dev


def test_license_file_and_pyproject_field_say_mit():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("MIT License")
    assert "Copyright (c) 2026 Ольга Щербань (YTMOlga)" in license_text
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "MIT"' in pyproject
    assert 'license-files = ["LICENSE"]' in pyproject
