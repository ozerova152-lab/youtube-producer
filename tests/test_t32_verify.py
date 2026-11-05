"""T32 (независимая проверка): настоящий бинарник `produce` в подпроцессе, часы компьютера подменены."""

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"
BIN = ROOT / ".venv" / "bin" / "produce"
WARN = "`fixed_date` игнорируется: это не демо-канал. Удалите строку из settings.yaml"

pytestmark = pytest.mark.skipif(not BIN.exists(), reason="нет .venv/bin/produce")


@pytest.fixture
def clock_dir(tmp_path):
    """sitecustomize подменяет datetime.now() в produce.core.clock (faketime в WSL нет)."""
    d = tmp_path / "_fake"
    d.mkdir()
    (d / "sitecustomize.py").write_text(textwrap.dedent("""
        import os
        from datetime import UTC, datetime
        y, m, dd = map(int, os.environ["FAKE_TODAY"].split("-"))
        class D(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(y, m, dd, 12, 0, tzinfo=tz or UTC)
        import produce.core.clock as c
        c.datetime = D
    """), encoding="utf-8")
    return d


def produce(clock_dir, today, channel, *args, now=None):
    env = {k: v for k, v in os.environ.items() if k not in ("PRODUCE_NOW", "YOUTUBE_API_KEY")}
    env.update(PYTHONPATH=str(clock_dir), FAKE_TODAY=today)
    if now:
        env["PRODUCE_NOW"] = now
    return subprocess.run([str(BIN), "--channel", str(channel), *args], capture_output=True, text=True, check=False,
                          env=env, cwd=str(clock_dir.parent), timeout=120)


def make(tmp_path, name):
    p = tmp_path / name
    shutil.copytree(DEMO, p)
    shutil.rmtree(p / "runs", ignore_errors=True)
    return p


@pytest.mark.parametrize("today", ["2026-10-30", "2026-11-21", "2026-11-22", "2027-03-15"])
def test_readme_demo_same_on_any_day(clock_dir, tmp_path, today):
    ch = make(tmp_path, "demo")
    s = produce(clock_dir, today, ch, "start", "--segment", "ru", "--brief-lang", "ru")
    assert s.returncode == 0, s.stderr
    assert "Дата зафиксирована для демо: 2026-10-27" in s.stdout
    assert (ch / "runs" / "2026-10_ru_v1").is_dir()
    i = produce(clock_dir, today, ch, "import", str(DEMO / "import_comments.json"), "--segment", "ru")
    assert "Загружено: 11 видео, 2 канала. Обращений к YouTube: 0" in i.stdout
    v = produce(clock_dir, today, ch, "virals", "--segment", "ru")
    assert v.returncode == 0 and "12.68" in v.stdout


def test_produce_now_stronger_in_real_binary(clock_dir, tmp_path):
    ch = make(tmp_path, "demo")
    s = produce(clock_dir, "2027-01-01", ch, "start", "--segment", "ru", "--brief-lang", "ru", now="2026-11-03")
    assert s.returncode == 0 and (ch / "runs" / "2026-11_ru_v1").is_dir()
    assert "Дата зафиксирована" not in s.stdout


def test_bad_fixed_date_in_demo_exit_1_no_traceback(clock_dir, tmp_path):
    ch = make(tmp_path, "demo")
    st = ch / "settings.yaml"
    st.write_text(st.read_text(encoding="utf-8").replace("fixed_date: 2026-10-27", "fixed_date: 'завтра'"),
                  encoding="utf-8")
    r = produce(clock_dir, "2026-12-01", ch, "segments")
    assert r.returncode == 1 and "Traceback" not in r.stdout + r.stderr
    assert "должно быть датой ГГГГ-ММ-ДД" in r.stdout + r.stderr


@pytest.mark.parametrize("name", ["my-channel", "demo-copy", "Demo", "demo2", "xdemo"])
def test_other_folder_ignores_fixed_date(clock_dir, tmp_path, name):
    ch = make(tmp_path, name)
    r = produce(clock_dir, "2026-12-01", ch, "segments")
    assert r.returncode == 0
    assert WARN in r.stderr and WARN not in r.stdout
    assert "Дата зафиксирована" not in r.stdout + r.stderr
    s = produce(clock_dir, "2026-12-01", ch, "start", "--segment", "ru", "--brief-lang", "ru")
    assert s.returncode == 0 and WARN in s.stderr and WARN not in s.stdout
    assert (ch / "runs" / "2026-12_ru_v1").is_dir() and not (ch / "runs" / "2026-10_ru_v1").exists()


def test_stdout_of_segments_identical_with_and_without_line(clock_dir, tmp_path):
    a = make(tmp_path, "chan-a")
    b = make(tmp_path, "chan-b")
    st = b / "settings.yaml"
    st.write_text("".join(x for x in st.read_text(encoding="utf-8").splitlines(keepends=True)
                          if not x.startswith("fixed_date:")), encoding="utf-8")
    ra = produce(clock_dir, "2026-12-01", a, "segments")
    rb = produce(clock_dir, "2026-12-01", b, "segments")
    assert ra.stdout == rb.stdout and rb.stderr == ""


def test_bad_fixed_date_outside_demo_warning_only(clock_dir, tmp_path):
    ch = make(tmp_path, "other")
    st = ch / "settings.yaml"
    st.write_text(st.read_text(encoding="utf-8").replace("fixed_date: 2026-10-27", "fixed_date: 'мусор'"),
                  encoding="utf-8")
    r = produce(clock_dir, "2026-12-01", ch, "segments")
    assert r.returncode == 0 and WARN in r.stderr


def test_symlink_named_differently_to_demo_resolves_to_demo(clock_dir, tmp_path):
    """Симлинк link -> .../demo: после resolve имя demo, значит дата зафиксирована (документируем поведение)."""
    real = make(tmp_path, "demo")
    link = tmp_path / "link"
    link.symlink_to(real)
    r = produce(clock_dir, "2026-12-01", link, "start", "--segment", "ru", "--brief-lang", "ru")
    assert r.returncode == 0 and "Дата зафиксирована для демо" in r.stdout


def test_symlink_named_demo_to_other_folder_is_not_demo(clock_dir, tmp_path):
    real = make(tmp_path, "my-channel")
    (tmp_path / "w").mkdir()
    link = tmp_path / "w" / "demo"
    link.symlink_to(real)
    r = produce(clock_dir, "2026-12-01", link, "segments")
    assert WARN in r.stderr


def test_conftest_channel_fixture_strips_only_the_line_and_demo_file_untouched():
    conf = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'startswith("fixed_date:")' in conf
    assert "fixed_date: 2026-10-27" in (DEMO / "settings.yaml").read_text(encoding="utf-8")


def test_compatibility_links_and_single_status():
    t = (ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8")
    assert "## Как поставить агента" in t
    for u in ("https://code.claude.com/docs/en/setup", "https://claude.com/download",
              "https://github.com/openai/codex"):
        assert u in t
    assert len(re.findall(r"^## Статус", t, re.MULTILINE)) == 1
    assert t.count("Основной путь — Claude Code, проверен полностью") == 1


def test_readme_key_steps_and_length():
    ru = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert len(ru.splitlines()) <= 165
    sec = ru.split("## Свой канал")[1]
    assert [int(n) for n in re.findall(r"^(\d)\. ", sec, re.MULTILINE)[:6]] == [1, 2, 3, 4, 5, 6]
    sec_en = en.split("## Your own channel")[1]
    assert [int(n) for n in re.findall(r"^(\d)\. ", sec_en, re.MULTILINE)[:6]] == [1, 2, 3, 4, 5, 6]


def test_spec_matches_code_texts():
    spec = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")
    assert WARN in spec
    assert "Дата зафиксирована для демо: 2026-10-27 (строка `fixed_date` в settings.yaml; для своего канала удалите её)" in spec
    assert "В `settings.yaml` поле `fixed_date` должно быть датой ГГГГ-ММ-ДД. Исправьте и повторите" in spec
