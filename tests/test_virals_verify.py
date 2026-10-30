"""Независимая проверка критериев T07 (поиск залётов), написана от критериев приёмки.

Числа в ожиданиях посчитаны здесь вручную, а не взяты из кода. Враждебные случаи: нулевая
медиана, нет лайков, равенство порогу, `|` и переводы строк в названии, ролики старше 30 дней,
трансляции, канал с малым числом роликов, ослабленные и сломанные пороги, повтор, нет сети.
"""

import csv
import hashlib
import json
import re
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import write_json_atomic

RUN = "2026-10_ru_v1"
ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    def no_net(*a, **k):
        raise AssertionError("Поиск залётов полез в сеть")

    monkeypatch.setattr(socket.socket, "connect", no_net)


def vid(vid_id, views, likes, comments, channel="UCx", published="2026-10-20T10:00:00Z",
        live=False, title=None):
    return {"id": vid_id, "title": title if title is not None else f"T {vid_id}",
            "description": "", "channel_id": channel, "channel_title": "Канал",
            "published_at": published, "duration_seconds": 600, "is_live": live,
            "views": views, "likes": likes, "comments": comments}


def base(channel_id, n=10, views=1000, first_day=1):
    """n обычных роликов с одинаковыми просмотрами (норма = views), старше кандидатов."""
    return [vid(f"{channel_id}_b{i}", views, 30, 3, channel_id,
                f"2026-10-{first_day + i:02d}T10:00:00Z") for i in range(n)]


def put(channel, videos, settings_patch=None):
    run = channel / "runs" / RUN
    (run / "cache").mkdir(parents=True)
    write_json_atomic(run / "cache" / "videos.json", {v["id"]: v for v in videos})
    write_json_atomic(run / "cache" / "channels.json", {})
    write_json_atomic(run / "run.json", {
        "month": "2026-10", "segment": "ru", "brief_lang": "ru", "version": 1, "stage": "собрано",
        "quota_spent": 0, "requests_count": 0, "awaiting_confirmation": False,
        "incomplete_data": []})
    return run


def virals(channel, *extra):
    return CliRunner().invoke(app, ["--channel", str(channel), "virals", "--segment", "ru",
                                    *extra])


def result(channel):
    return json.loads((channel / "runs" / RUN / "virals.json").read_text(encoding="utf-8"))


def ids(items):
    return sorted(v["id"] for v in items)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Критерий 1: ровно ожидаемые, с числами ---------------------------------------------

def test_exactly_expected_with_numbers(channel):
    vids = []
    # Норма каждого канала = 1000 (десять роликов по 1000). Кандидат: просмотры, лайки, комм.
    cases = {
        "good": (4000, 100, 8),      # 4x, 2.5%, 0.2% -> залёт
        "views2x": (2999, 200, 20),  # 2.999x -> нет
        "lowlike": (5000, 99, 20),   # 1.98% -> нет
        "lowcomm": (5000, 200, 4),   # 0.08% -> нет
    }
    for name, (v, lk, cm) in cases.items():
        vids += base(f"C_{name}")
        vids.append(vid(name, v, lk, cm, f"C_{name}"))
    run = put(channel, vids)
    r = virals(channel)
    assert r.exit_code == 0, r.output
    data = result(channel)
    assert ids(data["virals"]) == ["good"]
    g = data["virals"][0]
    assert (g["views"], g["norm"], g["times_norm"]) == (4000, 1000, 4.0)
    assert (g["likes"], g["comments"]) == (100, 8)
    assert g["likes_ratio"] == pytest.approx(0.025)
    assert g["comments_ratio"] == pytest.approx(0.002)
    assert data["nearest"] == []  # залёты есть, ближайшие не нужны
    assert (run / "run.json").read_text(encoding="utf-8").count("залёты") == 1


def test_candidate_not_in_own_norm(channel):
    # 10 по 1000 + кандидат 5000. Если кандидат попал в выборку, медиана была бы 1000 всё равно,
    # поэтому ставим 5 роликов по 100 и 5 по 1000: медиана без кандидата 550.
    vids = [vid(f"n{i}", 100 if i < 5 else 1000, 30, 3, "A", f"2026-10-{i + 1:02d}T10:00:00Z")
            for i in range(10)]
    vids.append(vid("cand", 1650, 60, 5, "A"))
    put(channel, vids)
    virals(channel)
    data = result(channel)
    assert ids(data["virals"]) == ["cand"]
    assert data["virals"][0]["norm"] == 550  # (100 .. 1000 медиана без кандидата)
    assert data["virals"][0]["times_norm"] == 3.0


# --- Критерий 2: мало данных ------------------------------------------------------------

def test_few_videos_skipped_with_note(channel):
    vids = base("SMALL", n=3) + [vid("s_cand", 99999, 5000, 500, "SMALL")]  # у канала 4 ролика
    vids += base("BIG") + [vid("b_cand", 4000, 100, 8, "BIG")]
    put(channel, vids)
    r = virals(channel)
    data = result(channel)
    assert ids(data["virals"]) == ["b_cand"]
    skipped = {s["id"]: s for s in data["skipped"]}
    assert "s_cand" in skipped and skipped["s_cand"]["reason"] == "мало данных"
    assert "Мало данных" in r.output


def test_five_total_videos_borderline(channel):
    # Критерий: «у канала меньше 5 роликов». У канала ровно 5 (проверяемое + 4 других).
    # Норму считаем «без проверяемого» -> 4. Фиксируем фактическое поведение как наблюдение.
    vids = base("FIVE", n=4) + [vid("f_cand", 9999, 500, 50, "FIVE")]
    put(channel, vids)
    virals(channel)
    data = result(channel)
    # Спека: «если роликов меньше 5, видео пропускается» -> при 5 пропуска быть не должно.
    assert "f_cand" not in [s["id"] for s in data["skipped"]], (
        "канал с ровно 5 загруженными роликами помечен «мало данных»")


# --- Критерий 3: ничего не прошло -> 5 ближайших, settings не меняется ----------------------

def test_nothing_passes_five_nearest_settings_hash_same(channel):
    vids = []
    for i in range(7):
        ch = f"N{i}"
        vids += base(ch) + [vid(f"c{i}", 1500 + 200 * i, 40 + 5 * i, 3, ch)]
    put(channel, vids)
    st = channel / "settings.yaml"
    before = sha(st)
    r = virals(channel)
    assert r.exit_code == 0, r.output
    assert sha(st) == before
    data = result(channel)
    assert data["virals"] == [] and len(data["nearest"]) == 5
    assert "Залётов нет" in r.output and "ослабить пороги" in r.output
    # Ближайшие — те, у кого лучший: c6 (3.0x? 2700 -> 2.7x) ... по убыванию близости
    near_ids = [v["id"] for v in data["nearest"]]
    assert near_ids[0] == "c6" and "c0" not in near_ids and "c1" not in near_ids
    closeness = [v["closeness"] for v in data["nearest"]]
    assert closeness == sorted(closeness, reverse=True)


def test_fewer_than_five_candidates_no_crash(channel):
    old = [vid(f"o{i}", 1000, 30, 3, "A", f"2026-08-{i + 1:02d}T10:00:00Z") for i in range(10)]
    put(channel, old + [vid("only", 1200, 30, 3, "A")])  # старые не кандидаты: кандидат один
    r = virals(channel)
    assert r.exit_code == 0
    assert [v["id"] for v in result(channel)["nearest"]] == ["only"]


# --- Критерий 4: норма из 12 роликов -----------------------------------------------------

def test_norm_12_videos_checked_and_live_excluded(channel):
    # 12 роликов канала: проверяемое (cand), трансляция (live) и 10 обычных.
    # Обычные просмотры 100,200,...,1000 -> медиана 550. Трансляция 1_000_000 исказила бы норму.
    vids = [vid(f"r{i}", 100 * (i + 1), 30, 3, "Z", f"2026-10-{i + 1:02d}T10:00:00Z")
            for i in range(10)]
    vids.append(vid("live", 1_000_000, 30, 3, "Z", "2026-10-12T10:00:00Z", live=True))
    vids.append(vid("cand", 1650, 60, 5, "Z"))
    put(channel, vids)
    virals(channel)
    data = result(channel)
    cand = data["virals"][0]
    assert cand["id"] == "cand" and cand["norm"] == 550 and cand["norm_sample"] == 10
    assert "live" not in ids(data["virals"]) + ids(data["nearest"])


def test_norm_takes_only_10_latest(channel):
    # 15 обычных: 5 самых старых по 1_000_000 не должны попасть в выборку.
    old = [vid(f"o{i}", 1_000_000, 30, 3, "Y", f"2026-09-{i + 1:02d}T10:00:00Z") for i in range(5)]
    recent = [vid(f"n{i}", 1000, 30, 3, "Y", f"2026-10-{i + 1:02d}T10:00:00Z") for i in range(10)]
    put(channel, old + recent + [vid("cand", 3500, 100, 5, "Y")])
    virals(channel)
    data = result(channel)
    assert ids(data["virals"]) == ["cand"]
    assert data["virals"][0]["norm"] == 1000


# --- Враждебные: ноль, лайки, граница, текст, давность -----------------------------------

def test_zero_median_no_crash(channel):
    put(channel, base("Q", views=0) + [vid("cand", 500, 50, 5, "Q")])
    r = virals(channel)
    assert r.exit_code == 0, f"{r.output!r} {r.exception!r}"
    assert "Traceback" not in r.output and "ZeroDivision" not in r.output
    data = result(channel)
    json.dumps(data)  # валидный JSON без NaN/inf
    assert "NaN" not in (channel / "runs" / RUN / "virals.json").read_text(encoding="utf-8")


def test_zero_median_report_no_crash(channel):
    put(channel, base("Q", views=0) + [vid("cand", 500, 50, 5, "Q")])
    virals(channel)
    rep = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert rep.exit_code == 0, f"{rep.output!r} {rep.exception!r}"


def test_zero_views_candidate_no_crash(channel):
    put(channel, base("Q") + [vid("zero", 0, 0, 0, "Q")])
    r = virals(channel)
    assert r.exit_code == 0, r.output
    assert "zero" not in ids(result(channel)["virals"])


def test_no_likes_none_and_zero(channel):
    put(channel, base("L") + [vid("nolikes", 5000, None, 10, "L"), vid("zerolikes", 5000, 0, 10, "L")])
    r = virals(channel)
    assert r.exit_code == 0, r.output
    data = result(channel)
    assert data["virals"] == []
    report = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert report.exit_code == 0, report.output


def test_exact_threshold_is_viral(channel):
    # ровно 3x, ровно 2%, ровно 0.1%
    put(channel, base("E") + [vid("eq", 3000, 60, 3, "E")])
    virals(channel)
    assert ids(result(channel)["virals"]) == ["eq"]


@pytest.mark.parametrize("views,likes,comments", [(2999, 60, 3), (3000, 59, 3), (3000, 60, 2)])
def test_just_below_threshold_not_viral(channel, views, likes, comments):
    put(channel, base("E") + [vid("below", views, likes, comments, "E")])
    virals(channel)
    assert result(channel)["virals"] == []


def test_title_with_pipe_and_newlines(channel):
    title = "A | B\nвторая строка\r\nтретья | ещё"
    put(channel, base("T") + [vid("pipe", 4000, 100, 8, "T", title=title)])
    virals(channel)
    data = result(channel)
    assert data["virals"][0]["title"] == title  # данные не искажаются
    rep = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert rep.exit_code == 0, rep.output
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    section = text.split("## Залёты", 1)[1]
    rows = [ln for ln in section.splitlines() if ln.startswith("|") and "pipe" in ln]
    assert len(rows) == 1, "строка таблицы разорвана переводом строки"
    # число несэкранированных разделителей = колонки (7 колонок -> 8 вертикальных черт)
    row = rows[0].replace("\\|", "")
    assert row.count("|") == 8, rows[0]
    # консольный вывод: каждый залёт одной строкой
    lines = [ln for ln in virals(channel).output.splitlines() if "просмотров" in ln]
    assert len(lines) == 1


def test_videos_older_than_30_days_not_candidates(channel):
    put(channel, base("OLD") + [
        vid("old", 50000, 2000, 200, "OLD", "2026-09-10T10:00:00Z"),   # 47 дней
        vid("fresh", 4000, 100, 8, "OLD", "2026-10-02T10:00:00Z")])    # 25 дней
    virals(channel)
    data = result(channel)
    assert ids(data["virals"]) == ["fresh"]
    assert "old" not in ids(data["nearest"]) + [s["id"] for s in data["skipped"]]


def test_old_videos_still_feed_the_norm(channel):
    # Ролики старше 30 дней нужны для нормы: 10 старых по 1000 + свежий кандидат
    old = [vid(f"o{i}", 1000, 30, 3, "W", f"2026-08-{i + 1:02d}T10:00:00Z") for i in range(10)]
    put(channel, old + [vid("cand", 4000, 100, 8, "W")])
    virals(channel)
    assert ids(result(channel)["virals"]) == ["cand"]


def test_live_is_not_a_candidate(channel):
    put(channel, base("V") + [vid("stream", 9000, 500, 50, "V", live=True)])
    virals(channel)
    data = result(channel)
    assert data["virals"] == []
    assert "stream" not in ids(data["nearest"])


# --- Настройки: пороги из settings, мусор, неизменность ------------------------------------

def test_thresholds_from_settings_honoured(channel):
    st = channel / "settings.yaml"
    st.write_text(st.read_text(encoding="utf-8").replace("views_multiplier: 3", "views_multiplier: 1.5"),
                  encoding="utf-8")
    put(channel, base("S") + [vid("c", 1600, 40, 3, "S")])
    before = sha(st)
    virals(channel)
    assert ids(result(channel)["virals"]) == ["c"]
    assert sha(st) == before


def test_broken_thresholds_human_error_settings_intact(channel):
    st = channel / "settings.yaml"
    st.write_text(st.read_text(encoding="utf-8").replace("views_multiplier: 3", "views_multiplier: много"),
                  encoding="utf-8")
    put(channel, base("S") + [vid("c", 4000, 100, 8, "S")])
    before = sha(st)
    r = virals(channel)
    assert r.exit_code == 1 and "Traceback" not in r.output and "thresholds" in r.output
    assert sha(st) == before


def test_no_run_and_no_segment_errors(channel):
    r = virals(channel)  # запуска нет
    assert r.exit_code == 1 and "Traceback" not in r.output
    r2 = CliRunner().invoke(app, ["--channel", str(channel), "virals"])  # два сегмента, без --segment
    assert r2.exit_code == 1 and "--segment" in r2.output


def test_repeat_is_idempotent(channel):
    put(channel, base("R") + [vid("c", 4000, 100, 8, "R")])
    virals(channel)
    first = result(channel)
    virals(channel)
    assert result(channel) == first


# --- Критерий 6: импорт --------------------------------------------------------------------

def test_import_then_virals_matches_manual_calculation(channel):
    imp = CliRunner().invoke(app, ["--channel", str(channel), "import",
                                   str(DEMO / "import.csv"), "--segment", "ru"])
    assert imp.exit_code == 0, imp.output
    r = virals(channel)
    assert r.exit_code == 0, r.output
    rows = list(csv.DictReader((DEMO / "import.csv").open(encoding="utf-8")))
    # независимый расчёт: для каждого канала норма = медиана просмотров остальных обычных роликов
    from statistics import median
    expected = {}
    for row in rows:
        if row["is_live"] not in ("нет", "false", "False", "0", ""):
            continue
        same = [int(x["views"]) for x in rows if x["channel_id"] == row["channel_id"]
                and x["id"] != row["id"] and x["is_live"] in ("нет", "false", "False", "0", "")]
        if len(same) < 5:
            continue
        norm = median(same)
        v, lk, cm = int(row["views"]), int(row["likes"]), int(row["comments"])
        if row["published_at"] >= "2026-09-27" and v >= 3 * norm and lk / v >= 0.02 and cm / v >= 0.001:
            expected[row["id"]] = norm
    data = result(channel)
    assert expected, "в демо-файле нет ожидаемых залётов — тест бессмыслен"
    assert {v["id"]: v["norm"] for v in data["virals"]} == {k: round(n) for k, n in expected.items()}


# --- Критерий 7: скорость в день не влияет на отбор -----------------------------------------

def test_views_per_day_is_recorded_but_not_selecting(channel, tmp_path):
    # Те же просмотры/лайки/комментарии, разные даты (скорость в день разная).
    put(channel, base("P") + [vid("fast", 4000, 100, 8, "P", "2026-10-26T10:00:00Z"),
                              vid("slow", 4000, 100, 8, "P", "2026-09-30T10:00:00Z")])
    virals(channel)
    data = result(channel)
    by = {v["id"]: v for v in data["virals"]}
    assert set(by) == {"fast", "slow"}                      # отбор одинаков
    assert by["fast"]["views_per_day"] > by["slow"]["views_per_day"] > 0   # сигнал записан
    # Порядок не по скорости, а по кратности нормы (равны) -> стабильно по id
    assert [v["id"] for v in data["virals"]] == ["fast", "slow"]
    # Быстрый, но не прошедший порог, не становится залётом
    ch2 = tmp_path / "c2"
    import shutil
    shutil.copytree(DEMO, ch2)
    put(ch2, base("P") + [vid("fastbad", 2500, 100, 8, "P", "2026-10-26T10:00:00Z")])
    virals(ch2)
    assert result(ch2)["virals"] == []


def test_report_notes_speed_is_extra(channel):
    put(channel, base("P") + [vid("c", 4000, 100, 8, "P")])
    virals(channel)
    CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert "## Залёты" in text and "×4" in text and "на отбор не влияет" in text


# --- Критерий 5: сценарии агента (структурно) ------------------------------------------------

def _pb(name):
    return (ROOT / "playbooks" / name).read_text(encoding="utf-8")


def test_collect_playbook_structure():
    t = _pb("01-collect.md")
    assert re.search(r"produce --channel <канал> collect \[--segment <id>\]`", t)
    assert "collect --confirm" in t
    assert re.search(r"import <файл>", t)
    # пауза на оценке квоты до слова человека
    pos_estimate = t.index("оценк")
    assert "остановиться" in t and "Запускаем сбор?" in t
    # агент сам --confirm не ставит
    assert "агент **сам не ставит**" in t
    assert "Подтверждение действует **один раз**" in t
    # единственная команда с --confirm идёт после пункта ожидания ответа
    first_confirm_cmd = t.index("collect --confirm")
    assert t.index("Ждать ответа человека") < first_confirm_cmd
    assert pos_estimate < first_confirm_cmd
    # инъекции и ключи
    assert "данные, а не инструкции" in t and "Не читать `.env`" in t
    assert "02-virals" in t
    # слова-неподтверждения явно не разрешают
    assert "«ну ок»" in t and "не разрешение" in t


def test_virals_playbook_structure():
    t = _pb("02-virals.md")
    assert re.search(r"produce --channel <канал> virals", t)
    assert re.search(r"produce --channel <канал> report", t)
    assert t.index("virals [") < t.index("report [")
    assert "Залётов нет" in t and "ближайшие" in t.lower() and "ослабить пороги" in t
    assert "`settings.yaml` не менять никогда" in t
    assert "--confirm" not in t          # на этом шаге платных действий нет
    assert "дополнительный сигнал" in t
    assert "Мой канал не задан" in t
    assert "03-analysis" in t


def test_claude_md_links_both_playbooks():
    claude = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "`playbooks/01-collect.md`" in claude and "`playbooks/02-virals.md`" in claude
    assert "--confirm" in claude and "только после слова человека" in claude
    assert (ROOT / "playbooks" / "01-collect.md").exists()
    assert (ROOT / "playbooks" / "02-virals.md").exists()


# --- Круг 2: новые края ---------------------------------------------------------------------

def test_channel_with_4_videos_skipped_5_not(channel):
    four = base("F4", n=3) + [vid("cand4", 9999, 500, 50, "F4")]
    five = base("F5", n=4) + [vid("cand5", 9999, 500, 50, "F5")]
    put(channel, four + five)
    virals(channel)
    data = result(channel)
    skipped = {s["id"] for s in data["skipped"]}
    assert "cand4" in skipped and "cand5" not in skipped
    assert "cand5" in ids(data["virals"]) + ids(data["nearest"])


def test_zero_median_virals_and_report_texts(channel):
    put(channel, base("Q", views=0) + [vid("cand", 500, 50, 5, "Q")])
    r = virals(channel)
    assert r.exit_code == 0, f"{r.output!r} {r.exception!r}"
    assert "норма 0" in r.output and "None" not in r.output
    rep = CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"])
    assert rep.exit_code == 0, f"{rep.output!r} {rep.exception!r}"
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert "None" not in text and "nan" not in text.lower()
