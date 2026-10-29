"""T17 (независимая проверка): `start` на «плане готов» спрашивает, v2 только с `--new-version`."""
import hashlib
from pathlib import Path

from typer.testing import CliRunner

from produce.cli import app
from produce.core import runs
from produce.core.files import read_json, write_json_atomic

ROOT = Path(__file__).parent.parent


def start(channel, *extra, segment="ru", month="2026-11"):
    return CliRunner().invoke(app, [
        "--channel", str(channel), "start", "--segment", segment, "--brief-lang", segment,
        "--month", month, *extra])


def snap(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "<dir>"
    return out


def done(channel, month="2026-11", segment="ru", quota=0, force=False):
    r = runs.start_run(channel, month, segment, segment, force_new_version=force).run
    (r.path / "cache" / "x.json").write_text('{"k": 1}', encoding="utf-8")
    r.data["quota_spent"] = quota
    write_json_atomic(r.path / "run.json", r.data)
    runs.set_stage(r, "план готов")
    return r


def test_ask_does_not_touch_v1_runjson_or_cache_bytes(channel):
    v1 = done(channel, quota=777)
    raw = (v1.path / "run.json").read_bytes()
    before = snap(channel)
    res = start(channel)
    assert res.exit_code == 0
    assert "Создать новую версию v2?" in res.output
    assert (v1.path / "run.json").read_bytes() == raw
    assert snap(channel) == before


def test_flag_makes_v2_quota_zero_cache_copied_v1_intact(channel):
    v1 = done(channel, quota=777)
    before = snap(v1.path)
    res = start(channel, "--new-version")
    assert res.exit_code == 0, res.output
    v2 = channel / "runs" / "2026-11_ru_v2"
    assert read_json(v2 / "run.json")["quota_spent"] == 0
    assert read_json(v2 / "run.json")["version"] == 2
    assert (v2 / "cache" / "x.json").read_text(encoding="utf-8") == '{"k": 1}'
    assert snap(v1.path) == before


def test_second_segment_finished_does_not_affect_first(channel):
    done(channel, segment="en")
    r = start(channel, segment="ru")
    assert "ещё нет запуска. Создаю" in r.output
    assert (channel / "runs" / "2026-11_ru_v1").is_dir()
    assert not (channel / "runs" / "2026-11_en_v2").exists()
    before = snap(channel)
    r = start(channel, segment="en")
    assert "Создать новую версию v2?" in r.output and r.exit_code == 0
    assert snap(channel) == before


def test_other_month_finished_new_month_creates_v1(channel):
    done(channel, month="2026-10")
    res = start(channel, month="2026-11")
    assert res.exit_code == 0
    assert (channel / "runs" / "2026-11_ru_v1").is_dir()
    assert not (channel / "runs" / "2026-10_ru_v2").exists()
    assert "Создать новую версию" not in res.output


def test_unfinished_with_flag_creates_v2(channel):
    v1 = runs.start_run(channel, "2026-11", "ru", "ru").run
    runs.set_stage(v1, "брифы на решение")
    res = start(channel, "--new-version")
    assert res.exit_code == 0
    assert (channel / "runs" / "2026-11_ru_v2").is_dir()


def test_flag_without_runs_creates_v1_not_v2(channel):
    res = start(channel, "--new-version")
    assert res.exit_code == 0, res.output
    assert (channel / "runs" / "2026-11_ru_v1").is_dir()
    assert not (channel / "runs" / "2026-11_ru_v2").exists()


def test_finished_v1_and_unfinished_v2_resumes_v2(channel):
    done(channel)
    v2 = runs.start_run(channel, "2026-11", "ru", "ru", force_new_version=True).run
    runs.set_stage(v2, "стратегия ждёт утверждения")
    before = snap(channel)
    res = start(channel)
    assert "Запуск 2026-11, ru, v2. Этап: стратегия ждёт утверждения. Продолжить?" in res.output
    assert snap(channel) == before


def test_v2_finished_asks_about_v3_with_twelve_runs(channel):
    for m in range(1, 11):
        done(channel, month=f"2026-{m:02d}")
    done(channel)
    done(channel, force=True)
    assert len(list((channel / "runs").iterdir())) == 12
    before = snap(channel)
    res = start(channel)
    assert res.exit_code == 0
    assert "уже есть v2, план готов. Создать новую версию v3?" in res.output
    assert "v1, план готов" not in res.output
    assert snap(channel) == before


def test_old_question_text_is_gone_everywhere():
    for rel in ("src/produce/cli.py", "playbooks/00-month.md", "playbooks/07-history.md",
                "docs/spec/04-user-flows.md"):
        assert "создам новую версию, кэш скопирую" not in (ROOT / rel).read_text(encoding="utf-8")


def test_playbooks_say_ask_human_and_flag_only_after_word():
    for name in ("00-month.md", "07-history.md"):
        text = (ROOT / "playbooks" / name).read_text(encoding="utf-8")
        assert "Создать новую версию v2?" in text, name
        assert "остановиться" in text.lower(), name
        assert "только после" in text and "«да»" in text and "в этом разговоре" in text, name
        assert "без слова" in text or "без слова человека" in text, name
