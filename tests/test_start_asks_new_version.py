"""T17: `start` на запуске «план готов» спрашивает человека и сам v2 не создаёт."""
import hashlib
from pathlib import Path

from typer.testing import CliRunner

from produce.cli import app
from produce.core import runs
from produce.core.files import read_json

QUESTION_V1 = (
    "В этом месяце уже есть v1, план готов. Создать новую версию v2? "
    "Кэш скопируется, квота не тратится. Напишите «да», и я создам"
)


def start(channel, *extra):
    return CliRunner().invoke(app, [
        "--channel", str(channel), "start", "--segment", "ru", "--brief-lang", "ru",
        "--month", "2026-11", *extra])


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()} | {
        str(p.relative_to(root)) + "/": "" for p in root.rglob("*") if p.is_dir()}


def finished_v1(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    (v1.path / "cache" / "videos.json").write_text('{"a": 1}', encoding="utf-8")
    runs.set_stage(v1, "план готов")
    return v1


def test_finished_run_asks_and_writes_nothing(channel):
    v1 = finished_v1(channel)
    before = snapshot(channel)
    res = start(channel)
    assert res.exit_code == 0, res.output
    assert QUESTION_V1 in res.output
    assert "создам новую версию" not in res.output
    assert snapshot(channel) == before
    assert not (channel / "runs" / "2026-11_ru_v2").exists()
    assert read_json(v1.path / "run.json")["stage"] == "план готов"


def test_repeated_question_is_stable(channel):
    finished_v1(channel)
    before = snapshot(channel)
    for _ in range(3):
        assert QUESTION_V1 in start(channel).output
    assert snapshot(channel) == before


def test_new_version_flag_creates_v2_with_cache_and_zero_quota(channel):
    v1 = finished_v1(channel)
    v1_before = snapshot(v1.path)
    res = start(channel, "--new-version")
    assert res.exit_code == 0, res.output
    v2 = channel / "runs" / "2026-11_ru_v2"
    assert (v2 / "cache" / "videos.json").read_text(encoding="utf-8") == '{"a": 1}'
    assert read_json(v2 / "run.json")["quota_spent"] == 0
    assert snapshot(v1.path) == v1_before


def test_unfinished_run_resumes_without_v2(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    runs.set_stage(v1, "стратегия ждёт утверждения")
    before = snapshot(channel)
    res = start(channel)
    assert res.exit_code == 0
    assert "Запуск 2026-11, ru, v1. Этап: стратегия ждёт утверждения. Продолжить?" in res.output
    assert "Создать новую версию" not in res.output
    assert snapshot(channel) == before


def test_question_names_latest_version_among_many_runs(channel):
    for month in ("2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"):
        for seg in ("ru", "en"):
            r = runs.start_run(channel, month, seg, seg).run
            runs.set_stage(r, "план готов")
    v1 = finished_v1(channel)
    v2 = runs.start_run(channel, "2026-11", "ru", "ru", force_new_version=True).run
    runs.set_stage(v2, "план готов")
    assert v1.path.exists()
    before = snapshot(channel)
    res = start(channel)
    assert res.exit_code == 0, res.output
    assert "В этом месяце уже есть v2, план готов. Создать новую версию v3?" in res.output
    assert snapshot(channel) == before
    assert not (channel / "runs" / "2026-11_ru_v3").exists()


def test_no_runs_creates_v1(channel):
    res = start(channel)
    assert res.exit_code == 0
    assert "ещё нет запуска. Создаю…" in res.output
    assert (channel / "runs" / "2026-11_ru_v1" / "run.json").exists()


def test_core_returns_ask_action_without_writing(channel):
    finished_v1(channel)
    before = snapshot(channel)
    result = runs.start_run(channel, "2026-11", "ru", "ru")
    assert result.action == "ask_new_version" and result.run.data["version"] == 1
    assert snapshot(channel) == before


def test_playbooks_require_human_word_before_flag():
    root = Path(__file__).parent.parent
    for name in ("00-month.md", "07-history.md"):
        text = (root / "playbooks" / name).read_text(encoding="utf-8")
        assert QUESTION_V1 in text
        assert "только после слова" in text and "--new-version" in text
