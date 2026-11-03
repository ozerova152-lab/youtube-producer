"""Обзор запуска `00-overview.md` (T23): состав, даты, обновление после команд, безопасность."""

import json
import re

import pytest
from typer.testing import CliRunner

from produce.cli import app
from produce.core import history, overview, runs
from produce.core.files import read_json, write_json_atomic

RUN = "2026-10_ru_v1"
SECRET = "AIzaSyTESTKEY-do-not-leak"
ORDER = ["Залётные ролики", "Разбор", "Ниша", "Конкуренты", "Стратегия", "Брифы и сценарии", "План"]


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def cli(channel, *args):
    # В демо-канале несколько сегментов: везде берём ru.
    extra = [] if args[0] in ("start", "segments") else ["--segment", "ru"]
    return CliRunner().invoke(app, ["--channel", str(channel), *args, *extra])


def started(channel):
    res = cli(channel, "start", "--segment", "ru", "--brief-lang", "ru")
    assert res.exit_code == 0, res.output
    return channel / "runs" / RUN


def text(run_dir):
    return (run_dir / "00-overview.md").read_text(encoding="utf-8")


def item_line(body, title):
    return next(line for line in body.splitlines() if re.match(rf"^\d+б?\. {title} ", line))


def test_run_json_gets_started_on_once_and_keeps_other_fields(channel):
    run_dir = started(channel)
    data = read_json(run_dir / "run.json")
    assert data["started_on"] == "2026-10-27" and "collected_on" not in data
    assert {"month", "segment", "brief_lang", "version", "stage", "quota_spent", "requests_count",
            "awaiting_confirmation", "incomplete_data"} <= set(data)
    assert sorted(p.name for p in run_dir.iterdir()) == ["00-overview.md", "cache", "run.json"]


def test_fresh_run_lists_seven_points_in_order_all_pending(channel):
    body = text(started(channel))
    assert "# Обзор запуска 2026-10_ru_v1" in body
    assert "сегмент ru, версия 1, этап: настроен" in body
    assert "Запуск начат: 2026-10-27." in body
    assert "Последний сбор данных: ещё не было." in body
    assert "Расход квоты: 0 из 10 000." in body
    assert "не правьте его" in body
    pos = [body.find(f". {t} ") for t in ORDER]
    assert all(p >= 0 for p in pos) and pos == sorted(pos)
    for title in ORDER:
        assert "⏳ ещё не сделано" in item_line(body, title)
    assert "Обложки" not in body
    assert "`run.json`, `cache/`" in body


def test_after_collect_virals_report_and_analysis_links_point_to_existing_files(channel):
    res = cli(channel, "import", str(channel / "import.csv"))
    assert res.exit_code == 0, res.output
    run_dir = channel / "runs" / RUN
    assert read_json(run_dir / "run.json")["collected_on"] == "2026-10-27"
    assert "Последний сбор данных: 2026-10-27." in text(run_dir)
    assert cli(channel, "virals").exit_code == 0
    assert cli(channel, "report").exit_code == 0
    (run_dir / "analysis.md").write_text("разбор", encoding="utf-8")
    assert overview.write(runs.load_run(run_dir))
    body = text(run_dir)
    assert "этап: залёты" in body
    assert "✅" in item_line(body, "Залётные ролики")
    assert "✅" in item_line(body, "Разбор")
    assert "[`report.md`](report.md)" in body and "[`analysis.md`](analysis.md)" in body
    for rel in re.findall(r"\]\(([^)]+)\)", body):
        assert (run_dir / rel).exists()
        assert not rel.startswith("/") and ".." not in rel
    assert "заметно больше обычного для канала" in item_line(body, "Залётные ролики")
    assert "о чём пишут зрители под залётами" in item_line(body, "Разбор")
    assert "⏳ ещё не сделано" in item_line(body, "Ниша")


def test_no_virals_marks_analysis_skipped_not_pending(channel):
    run_dir = started(channel)
    write_json_atomic(run_dir / "virals.json", {"checked": 3, "virals": [], "nearest": []})
    assert cli(channel, "overview").exit_code == 0
    body = text(run_dir)
    assert "⏭ пропущено: залётов нет" in item_line(body, "Разбор")
    assert "⏳" in item_line(body, "Ниша")


def test_briefs_are_listed_as_links_one_per_file(channel):
    run_dir = started(channel)
    (run_dir / "briefs").mkdir()
    for name in ("01.md", "02.md", "notes.txt", "x.md"):
        (run_dir / "briefs" / name).write_text("# Бриф", encoding="utf-8")
    assert cli(channel, "overview").exit_code == 0
    body = text(run_dir)
    assert "✅" in item_line(body, "Брифы и сценарии")
    assert "[`briefs/01.md`](briefs/01.md)" in body and "[`briefs/02.md`](briefs/02.md)" in body
    assert "notes.txt" not in body and "x.md" not in body


def test_covers_point_appears_only_with_covers_md_between_analysis_and_niche(channel):
    run_dir = started(channel)
    (run_dir / "covers.md").write_text("обложки", encoding="utf-8")
    assert cli(channel, "overview").exit_code == 0
    body = text(run_dir)
    assert "[`covers.md`](covers.md)" in body
    assert "✅" in item_line(body, "Обложки")
    assert body.index(". Разбор ") < body.index(". Обложки ") < body.index(". Ниша ")
    assert item_line(body, "Обложки").startswith("2б.")
    pos = [body.find(f". {t} ") for t in ORDER]
    assert pos == sorted(pos)
    (run_dir / "covers.md").unlink()
    assert cli(channel, "overview").exit_code == 0
    assert "Обложки" not in text(run_dir) and "covers.md" not in text(run_dir)


def test_deleted_or_renamed_overview_does_not_break_commands_and_is_recreated(channel):
    run_dir = started(channel)
    (run_dir / "00-overview.md").rename(run_dir / "old-overview.md")
    assert cli(channel, "segments").exit_code == 0
    assert cli(channel, "check-files").exit_code != 0  # файлов агента нет: красно, как и раньше
    assert "00-overview" not in cli(channel, "check-files").output
    (run_dir / "old-overview.md").unlink()
    assert not (run_dir / "00-overview.md").exists()
    res = cli(channel, "overview")
    assert res.exit_code == 0 and "Обзор записан" in res.output
    assert (run_dir / "00-overview.md").is_file()
    assert history.overview(channel, "ru", None).runs_count == 1  # обзор не мешает истории


def test_old_run_without_dates_says_date_unknown_and_invents_nothing(channel):
    run_dir = channel / "runs" / RUN
    (run_dir / "cache").mkdir(parents=True)
    write_json_atomic(run_dir / "run.json", {
        "month": "2026-10", "segment": "ru", "brief_lang": "ru", "version": 1,
        "stage": "собрано", "quota_spent": 640, "requests_count": 9,
        "awaiting_confirmation": False, "incomplete_data": []})
    res = cli(channel, "overview")
    assert res.exit_code == 0, res.output
    body = text(run_dir)
    assert "Запуск начат: дата неизвестна." in body
    assert "Последний сбор данных: дата неизвестна." in body
    assert "Расход квоты: 640 из 10 000." in body
    assert "2026-10-27" not in body
    assert "started_on" not in read_json(run_dir / "run.json")  # run.json не дописывается


def test_old_run_before_collection_says_collection_not_yet(channel):
    run_dir = channel / "runs" / RUN
    (run_dir / "cache").mkdir(parents=True)
    write_json_atomic(run_dir / "run.json", {
        "month": "2026-10", "segment": "ru", "brief_lang": "ru", "version": 1,
        "stage": "настроен", "quota_spent": 0, "requests_count": 0,
        "awaiting_confirmation": False, "incomplete_data": []})
    assert cli(channel, "overview").exit_code == 0
    assert "Последний сбор данных: ещё не было." in text(run_dir)


def test_overview_without_run_gives_human_error(channel):
    res = cli(channel, "overview")
    assert res.exit_code == 1 and "ещё нет" in res.output


def test_rebuild_is_byte_identical_and_atomic(channel):
    run_dir = started(channel)
    assert cli(channel, "import", str(channel / "import.csv")).exit_code == 0
    first = (run_dir / "00-overview.md").read_bytes()
    for _ in range(2):
        assert cli(channel, "overview").exit_code == 0
        assert (run_dir / "00-overview.md").read_bytes() == first
    assert not [p for p in run_dir.iterdir() if p.name.endswith(".tmp")]


def test_commands_refresh_overview_by_themselves(channel):
    run_dir = started(channel)
    assert "этап: настроен" in text(run_dir)
    assert cli(channel, "import", str(channel / "import.csv")).exit_code == 0
    assert "этап: собрано" in text(run_dir)
    assert cli(channel, "virals").exit_code == 0
    assert "этап: залёты" in text(run_dir)
    (run_dir / "report.md").unlink(missing_ok=True)
    assert cli(channel, "report").exit_code == 0
    assert "[`report.md`](report.md)" in text(run_dir)


def test_check_files_ignores_overview_and_red_check_does_not_touch_it(channel):
    run_dir = started(channel)
    (run_dir / "covers.md").write_text("не по шаблону", encoding="utf-8")
    (run_dir / "00-overview.md").unlink()
    res = cli(channel, "check-files", "--step", "covers")
    assert res.exit_code == 1 and "00-overview" not in res.output
    assert not (run_dir / "00-overview.md").exists()  # красная проверка обзор не трогает


def test_overview_has_no_key_comments_titles_or_outside_paths(channel, tmp_path):
    (channel / ".env").write_text(f"YOUTUBE_API_KEY={SECRET}\n", encoding="utf-8")
    run_dir = started(channel)
    assert cli(channel, "import", str(channel / "import.csv")).exit_code == 0
    assert cli(channel, "virals").exit_code == 0
    body = text(run_dir)
    assert SECRET not in body and "YOUTUBE_API_KEY" not in body
    virals = read_json(run_dir / "virals.json")
    titles = [v["title"] for v in virals["virals"]] + [v["title"] for v in virals["nearest"]]
    cache_titles = [v["title"] for v in read_json(run_dir / "cache" / "videos.json").values()]
    for title in titles + cache_titles:
        assert title not in body
    comments = read_json(run_dir / "cache" / "comments.json") if (run_dir / "cache" / "comments.json").exists() else {}
    for chunk in json.dumps(comments, ensure_ascii=False).split('"'):
        if len(chunk) > 25:
            assert chunk not in body
    assert str(tmp_path) not in body and "/home/" not in body
    mode = (run_dir / "00-overview.md").stat().st_mode & 0o777
    assert mode == 0o644 or mode == 0o600 or mode & 0o077 == mode & 0o044


def test_overview_does_not_need_network_or_key(channel, monkeypatch):
    run_dir = started(channel)

    def boom(*a, **k):
        raise AssertionError("сеть не нужна")

    import socket
    monkeypatch.setattr(socket, "socket", boom)
    assert cli(channel, "overview").exit_code == 0
    assert (run_dir / "00-overview.md").exists()


def test_green_check_files_and_later_refresh_overview(channel):
    from conftest import DEMO
    assert cli(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    assert cli(channel, "virals").exit_code == 0
    run_dir = channel / "runs" / RUN
    (run_dir / "analysis.md").write_text((DEMO / "expected" / "analysis.md").read_text(encoding="utf-8"),
                                         encoding="utf-8")
    (run_dir / "00-overview.md").unlink()
    assert cli(channel, "check-files").exit_code == 0
    assert "этап: разбор готов" in text(run_dir)
    (run_dir / "strategy.md").write_text((DEMO / "expected" / "strategy.md").read_text(encoding="utf-8"),
                                         encoding="utf-8")
    (run_dir / "00-overview.md").unlink()
    assert cli(channel, "check-files", "--step", "strategy").exit_code == 0
    body = text(run_dir)
    assert "этап: стратегия ждёт утверждения" in body
    assert "✅" in item_line(body, "Стратегия")


def test_later_refreshes_overview_with_returned_brief(channel):
    from test_history import make_run
    started(channel)
    run_dir = channel / "runs" / RUN
    make_run(channel, "2026-09_ru_v1", briefs={3: ("Один вопрос нейросети", "позже", "05.md")})
    assert not (run_dir / "briefs").exists()
    res = cli(channel, "later", "--pick", "1")
    assert res.exit_code == 0, res.output
    body = text(run_dir)
    assert "[`briefs/01.md`](briefs/01.md)" in body
    assert "Один вопрос нейросети" not in body  # названия брифов в обзор не идут


def test_agent_texts_name_the_overview_as_entry_point():
    from pathlib import Path
    root = Path(__file__).parent.parent
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "`00-overview.md`" in agents and "точкой входа" in agents
    assert "`00-overview.md`" in (root / "playbooks/00-month.md").read_text(encoding="utf-8")
    assert "`00-overview.md`" in (root / "README.md").read_text(encoding="utf-8")
