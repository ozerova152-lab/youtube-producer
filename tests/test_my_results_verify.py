"""Независимая проверка критериев T06 («Мои результаты»), написана от критериев приёмки.

Числа в ожиданиях посчитаны здесь вручную. Враждебные случаи: канал без роликов, 1/2/5/6/7 роликов
(лучшие и слабые не пересекаются), трансляции, нулевые просмотры и скрытые лайки, `|` и переводы
строк в названии, пустое/пробельное/нулевое `my_channel_id`, канал не найден, импорт без моего
канала, равные просмотры, повторный отчёт.
"""

import csv
import io
import json

import pytest
import yaml
from typer.testing import CliRunner

from produce.cli import app
from produce.core.collect import Cache
from produce.core.files import read_json
from produce.core.my_results import compute

RUN = "2026-10_ru_v1"
HEAD = ["id", "title", "channel_id", "channel_title", "channel_subscribers", "published_at",
        "views", "likes", "comments", "is_live"]
OTHER = [  # чужой канал: 5 обычных роликов, чтобы не быть пропущенным при импорте
    [f"o{i}", f"Чужой {i}", "UC_other", "Чужой", "500", f"2026-10-{10 + i:02d}T10:00:00Z",
     str(2000 + i), "20", "2", "нет"] for i in range(5)
]


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def invoke(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args])


def set_my(channel, value):
    path = channel / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if value is ...:
        data["channel"].pop("my_channel_id", None)
    else:
        data["channel"]["my_channel_id"] = value
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def mine(*rows):
    """rows: (id, title, views, likes, comments, is_live) -> строки CSV моего канала."""
    out = []
    for n, (vid, title, views, likes, comments, live) in enumerate(rows):
        out.append([vid, title, "UC_mine", "Мой", "300", f"2026-10-{1 + n:02d}T10:00:00Z",
                    str(views), likes, comments, "да" if live else "нет"])
    return out


def build(tmp_path, my_rows, with_other=True):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEAD)
    w.writerows(my_rows + (OTHER if with_other else []))
    f = tmp_path / "in.csv"
    f.write_text(buf.getvalue(), encoding="utf-8")
    return f


def run_import(channel, file):
    res = invoke(channel, "import", str(file), "--segment", "ru")
    assert res.exit_code == 0, res.output
    rep = invoke(channel, "report", "--segment", "ru")
    assert rep.exit_code == 0, rep.output
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    return text, read_json(channel / "runs" / RUN / "my_results.json")


def sect(text):
    return text.split("## Мои результаты", 1)[1]


def videos(n, start=1):
    return [(f"m{i}", f"Мой ролик {i}", i * 1000, "10", "1", False) for i in range(start, start + n)]


@pytest.mark.parametrize("n, best, weak", [(1, 1, 0), (2, 1, 1), (3, 2, 1), (4, 2, 2),
                                           (5, 3, 2), (6, 3, 3), (7, 3, 3)])
def test_best_and_weak_never_overlap(channel, tmp_path, n, best, weak):
    set_my(channel, "UC_mine")
    text, saved = run_import(channel, build(tmp_path, mine(*videos(n))))
    assert saved["status"] == "ok" and saved["videos"] == n
    assert (len(saved["best"]), len(saved["weak"])) == (best, weak)
    assert not {v["id"] for v in saved["best"]} & {v["id"] for v in saved["weak"]}
    # Лучший ролик — с наибольшими просмотрами, слабый первый — с наименьшими.
    assert saved["best"][0]["views"] == n * 1000
    if weak:
        assert saved["weak"][0]["views"] == 1000
    if not weak:
        assert "Слабых роликов нет" in sect(text)


def test_equal_views_ties_are_deterministic_and_disjoint(channel, tmp_path):
    set_my(channel, "UC_mine")
    rows = mine(*[(f"t{i}", f"Ничья {i}", 777, "1", "1", False) for i in range(6)])
    _, saved = run_import(channel, build(tmp_path, rows))
    ids = [v["id"] for v in saved["best"]] + [v["id"] for v in saved["weak"]]
    assert len(ids) == len(set(ids)) == 6


def test_live_streams_excluded(channel, tmp_path):
    set_my(channel, "UC_mine")
    rows = mine(*videos(6), ("live1", "Огромная трансляция", 5_000_000, "9", "9", True))
    text, saved = run_import(channel, build(tmp_path, rows))
    assert saved["videos"] == 6 and saved["best"][0]["views"] == 6000
    assert "Огромная трансляция" not in sect(text)


def test_channel_with_only_live_has_no_videos_note(channel, tmp_path):
    set_my(channel, "UC_mine")
    rows = mine(("l1", "Эфир", 100, "1", "1", True))
    text, saved = run_import(channel, build(tmp_path, rows))
    assert saved["status"] == "no_videos"
    assert "У моего канала нет роликов с открытой статистикой, пропускаю" in sect(text)
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0  # поток идёт дальше


def test_zero_views_and_hidden_likes_do_not_crash(channel, tmp_path):
    set_my(channel, "UC_mine")
    rows = mine(("z0", "Нулевой", 0, "", "", False), *videos(5, start=2))
    text, saved = run_import(channel, build(tmp_path, rows))
    zero = next(v for v in saved["weak"] if v["id"] == "z0")
    assert zero["views"] == 0 and zero["likes"] is None and zero["comments"] is None
    row = next(line for line in sect(text).splitlines() if "Нулевой" in line)
    assert "| 0 | — | — |" in row


def test_all_zero_views(channel, tmp_path):
    set_my(channel, "UC_mine")
    rows = mine(*[(f"z{i}", f"Ноль {i}", 0, "", "", False) for i in range(6)])
    _, saved = run_import(channel, build(tmp_path, rows))
    assert saved["status"] == "ok" and saved["median_views"] == 0


def test_pipe_in_title_csv(channel, tmp_path):
    set_my(channel, "UC_mine")
    rows = mine(("p1", "А | Б | В", 9000, "1", "1", False), *videos(5))
    text, _ = run_import(channel, build(tmp_path, rows))
    row = next(line for line in sect(text).splitlines() if "А / Б / В" in line)
    assert row.count("|") == 6  # 5 колонок: шесть разделителей


def test_newline_in_title_json(channel, tmp_path):
    set_my(channel, "UC_mine")
    vids = [{"id": f"j{i}", "title": "Строка один\nстрока два | хвост" if i == 5 else f"Ролик {i}",
             "channel_id": "UC_mine", "published_at": f"2026-10-{i + 1:02d}T10:00:00Z",
             "views": i * 100, "likes": 1, "comments": 1} for i in range(1, 7)]
    f = tmp_path / "in.json"
    f.write_text(json.dumps({"videos": vids, "channels": [
        {"id": "UC_mine", "title": "Мой", "subscribers": 10}]}), encoding="utf-8")
    text, _ = run_import(channel, f)
    row = next(line for line in sect(text).splitlines() if "Строка один" in line)
    assert "Строка один строка два / хвост" in row and row.count("|") == 6


@pytest.mark.xfail(strict=True, reason="importing._read_csv режет файл по splitlines(): перевод строки "
                   "внутри кавычек теряется без пробела (находка implementer, вне критериев T06)")
def test_newline_in_title_csv(channel, tmp_path):
    set_my(channel, "UC_mine")
    rows = mine(("n1", "Строка один\nстрока два", 9000, "1", "1", False), *videos(5))
    text, _ = run_import(channel, build(tmp_path, rows))
    assert any("Строка один строка два" in line for line in sect(text).splitlines())


@pytest.mark.parametrize("value", [...,  None, "", "   ", 0])
def test_my_channel_not_set_variants(channel, tmp_path, value):
    set_my(channel, value)
    text, saved = run_import(channel, build(tmp_path, mine(*videos(6))))
    if value == 0:  # 0 — строка "0": канала с таким id нет, но и падения быть не должно
        assert saved["status"] in ("not_set", "not_found")
    else:
        assert saved["status"] == "not_set"
        assert "## Мои результаты\n\nМой канал не задан, пропускаю." in text
    assert "UC_mine" not in sect(text) or value == 0


def test_my_channel_section_missing_channel_block_in_settings(channel, tmp_path):
    path = channel / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["channel"] = {k: v for k, v in data["channel"].items() if k != "my_channel_id"}
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    _, saved = run_import(channel, build(tmp_path, mine(*videos(6))))
    assert saved["status"] == "not_set"


def test_import_without_my_channel_json_and_flow_continues(channel, tmp_path):
    set_my(channel, "UC_ghost")
    text, saved = run_import(channel, build(tmp_path, mine(*videos(6))))
    assert saved["status"] == "not_found"
    assert "Моего канала нет в файле импорта, пропускаю." in sect(text)
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0
    assert "Ошибка" not in text and "Traceback" not in text


def test_import_ghost_channel_does_not_leak_other_channels(channel, tmp_path):
    set_my(channel, "UC_ghost")
    text, _ = run_import(channel, build(tmp_path, mine(*videos(6))))
    assert "Чужой 4" not in sect(text) and "Мой ролик" not in sect(text)


def test_collect_channel_not_found_note(tmp_path):
    cache = Cache(tmp_path / "cache")
    cache.videos["x"] = {"id": "x", "channel_id": "UC_a", "views": 5, "title": "t"}
    res = compute(cache, "UC_missing", "collect")
    assert res["status"] == "not_found"
    assert res["note"] == ("Мой канал не найден на YouTube (проверьте `my_channel_id` в "
                           "`settings.yaml`), пропускаю")


def test_collect_channel_found_but_no_videos(tmp_path):
    cache = Cache(tmp_path / "cache")
    cache.channels["UC_mine"] = {"id": "UC_mine", "title": "Мой"}
    res = compute(cache, "UC_mine", "collect")
    assert res["status"] == "no_videos" and res["best"] == [] and res["weak"] == []


def test_video_without_views_ignored(tmp_path):
    cache = Cache(tmp_path / "cache")
    cache.channels["UC_mine"] = {"id": "UC_mine", "title": "Мой"}
    cache.videos["h"] = {"id": "h", "channel_id": "UC_mine", "views": None, "title": "скрыто"}
    assert compute(cache, "UC_mine")["status"] == "no_videos"


def test_report_is_idempotent(channel, tmp_path):
    set_my(channel, "UC_mine")
    f = build(tmp_path, mine(*videos(6)))
    first, _ = run_import(channel, f)
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    second = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert first == second


def test_settings_not_modified_by_import_and_report(channel, tmp_path):
    before = (channel / "settings.yaml").read_bytes()
    run_import(channel, build(tmp_path, mine(*videos(6))))
    assert (channel / "settings.yaml").read_bytes() == before


@pytest.mark.vcr("collect_ru.yaml")
def test_collect_end_to_end_numbers_and_request_count(channel, tmp_path):
    """Критерий 1: демо-канал UC_demo_a на записанных ответах."""
    env = tmp_path / ".env"
    env.write_text("YOUTUBE_API_KEY=CANARY-xyz\n", encoding="utf-8")
    res = invoke(channel, "collect", "--segment", "ru", "--env-file", str(env), "--confirm")
    assert res.exit_code == 0, res.output
    assert read_json(channel / "runs" / RUN / "run.json")["requests_count"] == 10  # регрессия T03
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert "## Залёты" in text and "## Мои результаты" in text
    body = sect(text)
    assert "### Мои лучшие ролики" in body and "### Мои слабые ролики" in body
    assert "| 90 000 | 5 400 | 610 |" in body and "| 4 500 | 120 | 12 |" in body
    assert "CANARY" not in text
