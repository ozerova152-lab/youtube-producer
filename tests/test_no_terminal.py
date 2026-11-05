"""T28: режим без терминала. Формулы плейбука сверяются с кодом, тексты с спекой.

Эталонная реализация ниже написана по словам `playbooks/no-terminal.md` (числа берутся из его
таблицы), а не по коду. Она должна давать то же, что `virals.find` и `my_results.compute`.
"""

import random
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

import pytest

from produce.core import my_results, virals
from produce.core.collect import WINDOW_DAYS, Cache
from produce.core.files import write_json_atomic

ROOT = Path(__file__).parent.parent
PLAYBOOK = (ROOT / "playbooks/no-terminal.md").read_text(encoding="utf-8")
FLOWS = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")
L1 = (ROOT / "docs/spec/01-functional-requirements.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
CHAT_DOC = (ROOT / "docs/chat-mode.md").read_text(encoding="utf-8")  # T30: раздел «Если у вас только чат» переехал в docs
MOMENT = datetime(2026, 10, 27, tzinfo=UTC)

NO_TERMINAL_TEXT = (
    "В этом чате я не могу запускать программы и сохранять файлы, поэтому работаю в режиме без "
    "терминала. Я считаю по данным, которые вы вставите сюда или приложите, вручную и приблизительно. "
    "Результаты я выдаю текстом, а сохраняете их вы. Сбор с YouTube по ключу здесь недоступен, а ключ "
    "в чат вставлять не нужно. Начнём с данных: пришлите любые данные о видео вашей темы (таблицу, файл, "
    "выгрузку, скопированные ячейки Google Sheets), где есть названия, просмотры и даты. Формат из "
    "`docs/import-format.md` удобный пример, но не обязательное условие"
)
NORMAL_TEXT = "Работаю в обычном режиме: могу запускать команды проекта и сохранять файлы в `data/`"


# ---------- числа плейбука ----------

def playbook_constants() -> dict[str, float]:
    found = {}
    for name, value in re.findall(r"^\| `(\w+)`[^|]*\| ([\d,.]+) \|$", PLAYBOOK, re.MULTILINE):
        found[name] = float(value.replace(",", "."))
    return found


C = playbook_constants()


def test_playbook_constants_match_code():
    assert C["WINDOW_DAYS"] == WINDOW_DAYS == 30
    assert C["norm_videos"] == virals.DEFAULTS["norm_videos"]
    assert C["min_channel_videos"] == virals.DEFAULTS["min_channel_videos"]
    assert C["views_multiplier"] == virals.DEFAULTS["views_multiplier"]
    assert C["likes_ratio"] == virals.DEFAULTS["likes_ratio"]
    assert C["comments_ratio"] == virals.DEFAULTS["comments_ratio"]
    assert C["NEAREST"] == virals.NEAREST
    assert C["TOP"] == my_results.TOP
    assert set(C) == {"WINDOW_DAYS", "norm_videos", "min_channel_videos", "views_multiplier",
                      "likes_ratio", "comments_ratio", "NEAREST", "TOP"}


# ---------- эталон по словам плейбука ----------

def _date(video):
    moment = datetime.fromisoformat(video["published_at"])
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _regular(videos):
    return [v for v in videos if not v.get("is_live") and v.get("views") is not None]


def ref_virals(videos, moment=MOMENT):
    """Залёты, ближайшие и пропущенные: «Формулы» плейбука слово в слово."""
    since = moment - timedelta(days=C["WINDOW_DAYS"])
    checked, skipped = [], []
    for video in _regular(videos):
        if _date(video) < since:
            continue
        same = [v for v in _regular(videos) if v["channel_id"] == video["channel_id"]]
        if len(same) < C["min_channel_videos"]:
            skipped.append(video["id"])
            continue
        others = sorted((v for v in same if v["id"] != video["id"]), key=_date, reverse=True)
        sample = others[:int(C["norm_videos"])]
        norm = median(v["views"] for v in sample)
        views = video["views"]
        times = views / norm if norm > 0 else None
        likes, comments = video.get("likes"), video.get("comments")
        likes_r = likes / views if likes is not None and views > 0 else None
        comments_r = comments / views if comments is not None and views > 0 else None
        ok = (times is not None and times >= C["views_multiplier"]
              and likes_r is not None and likes_r >= C["likes_ratio"]
              and comments_r is not None and comments_r >= C["comments_ratio"])
        parts = [
            min(times / C["views_multiplier"], 1) if times is not None else 0,
            min(likes_r / C["likes_ratio"], 1) if likes_r is not None else 0,
            min(comments_r / C["comments_ratio"], 1) if comments_r is not None else 0,
        ]
        checked.append({"id": video["id"], "norm": round(norm),
                        "times": round(times, 2) if times is not None else None,
                        "close": min(parts), "ok": ok})
    viral = sorted((r for r in checked if r["ok"]), key=lambda r: (-(r["times"] or 0), r["id"]))
    rest = sorted((r for r in checked if not r["ok"]), key=lambda r: (-r["close"], r["id"]))
    nearest = [] if viral else rest[:int(C["NEAREST"])]
    return viral, nearest, sorted(skipped)


def ref_my_results(videos, my_channel):
    mine = [v for v in _regular(videos) if v["channel_id"] == my_channel]
    if not mine:
        return None
    ordered = sorted(mine, key=lambda v: (-v["views"], v["id"]))
    n, top = len(ordered), int(C["TOP"])
    best_n = min(top, (n + 1) // 2)
    weak_n = min(top, n - best_n)
    best = [v["id"] for v in ordered[:best_n]]
    weak = [v["id"] for v in reversed(ordered)][:weak_n]
    return best, weak, round(median(v["views"] for v in ordered))


# ---------- данные ----------

def vid(vid_id, channel, views, likes="auto", comments="auto", days_ago=5.0, live=False, moment=MOMENT):
    published = moment - timedelta(days=days_ago)
    return {"id": vid_id, "title": vid_id, "description": "", "channel_id": channel,
            "channel_title": channel, "published_at": published.isoformat(),
            "duration_seconds": 600, "is_live": live, "views": views,
            "likes": views // 20 if likes == "auto" else likes,
            "comments": views // 100 if comments == "auto" else comments}


def make_cache(tmp_path, videos, channels=()):
    directory = tmp_path / "cache"
    directory.mkdir(exist_ok=True)
    write_json_atomic(directory / "videos.json", {v["id"]: v for v in videos})
    write_json_atomic(directory / "channels.json", {c: {"title": c} for c in channels})
    return Cache(directory)


def same_as_code(cache, videos, th=None):
    th = th or virals.thresholds_from({})
    result = virals.find(cache, th, MOMENT)
    viral, nearest, skipped = ref_virals(videos)
    assert [r["id"] for r in result["virals"]] == [r["id"] for r in viral]
    assert [r["times_norm"] for r in result["virals"]] == [r["times"] for r in viral]
    assert [r["norm"] for r in result["virals"]] == [r["norm"] for r in viral]
    assert [r["id"] for r in result["nearest"]] == [r["id"] for r in nearest]
    assert sorted(s["id"] for s in result["skipped"]) == skipped
    return result


def base_channel(channel, n=10, views=1000, start=1.0, step=1.0):
    return [vid(f"{channel}_r{i}", channel, views + i, days_ago=start + i * step) for i in range(n)]


def test_demo_data_reference_equals_code(channel, monkeypatch):
    from typer.testing import CliRunner

    from conftest import DEMO
    from produce.cli import app

    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    out = CliRunner().invoke(app, ["--channel", str(channel), "import", str(DEMO / "import.csv"),
                                   "--segment", "ru"])
    assert out.exit_code == 0, out.output
    cache = Cache(channel / "runs" / "2026-10_ru_v1" / "cache")
    videos = list(cache.videos.values())
    result = same_as_code(cache, videos)
    assert [r["id"] for r in result["virals"]] == ["demo_v01"]
    mine = ref_my_results(videos, "UC_demo_a")
    code = my_results.compute(cache, "UC_demo_a", source="import")
    assert mine == ([v["id"] for v in code["best"]], [v["id"] for v in code["weak"]], code["median_views"])


def test_edge_live_is_ignored_for_norm_and_checks(tmp_path):
    videos = base_channel("A") + [vid("live", "A", 90000, days_ago=2, live=True)]
    result = same_as_code(make_cache(tmp_path, videos), videos)
    assert "live" not in [r["id"] for r in result["virals"]]
    # трансляция не попадает и в норму: с ней медиана была бы другой
    big = base_channel("B", n=5, views=100) + [vid("live2", "B", 10**6, days_ago=0.5, live=True)]
    same_as_code(make_cache(tmp_path, big), big)


def test_edge_unknown_likes_or_comments_means_condition_not_met(tmp_path):
    videos = (base_channel("A") + [vid("nolikes", "A", 20000, likes=None, comments=200, days_ago=0.1),
                                   vid("nocomm", "A", 20001, likes=800, comments=None, days_ago=0.2),
                                   vid("fine", "A", 20002, likes=800, comments=200, days_ago=0.3)])
    result = same_as_code(make_cache(tmp_path, videos), videos)
    assert [r["id"] for r in result["virals"]] == ["fine"]


def test_edge_norm_zero(tmp_path):
    videos = base_channel("Z", n=5, views=0, start=40) + [vid("zv", "Z", 100, likes=50, comments=10, days_ago=1)]
    videos = [v | {"views": 0} if v["id"].startswith("Z_r") else v for v in videos]
    result = same_as_code(make_cache(tmp_path, videos), videos)
    row = next(r for r in result["nearest"] if r["id"] == "zv")
    assert row["times_norm"] is None and virals.times_text(row) == "норма 0"
    assert "норма 0" in PLAYBOOK


def test_edge_few_data_and_exactly_five(tmp_path):
    four = base_channel("F", n=4, start=3)
    five = base_channel("G", n=5, start=3)
    videos = four + five
    result = same_as_code(make_cache(tmp_path, videos), videos)
    skipped = {s["id"] for s in result["skipped"]}
    assert skipped == {v["id"] for v in four}  # 4 ролика: «мало данных»; ровно 5: норма есть
    five_viral = five + [vid("g_big", "G", 20000, likes=900, comments=60, days_ago=0.5)]
    # шестое видео: теперь у канала 6 обычных, норма по остальным
    res = same_as_code(make_cache(tmp_path, five_viral), five_viral)
    assert [r["id"] for r in res["virals"]] == ["g_big"]


def test_edge_exactly_five_regular_includes_checked_video(tmp_path):
    # 5 обычных роликов, из них проверяемое: норма считается по четырём остальным
    five = [vid(f"E{i}", "E", 1000, days_ago=40 + i) for i in range(4)] + \
           [vid("E_new", "E", 4000, likes=200, comments=10, days_ago=1)]
    result = same_as_code(make_cache(tmp_path, five), five)
    assert [r["id"] for r in result["virals"]] == ["E_new"]
    assert result["virals"][0]["times_norm"] == 4.0


def test_edge_thirty_day_boundary(tmp_path):
    on_edge = vid("edge", "B", 5000, days_ago=C["WINDOW_DAYS"])
    late = on_edge | {"id": "late", "published_at": (MOMENT - timedelta(days=30, seconds=1)).isoformat()}
    videos = base_channel("B", n=6, start=40) + [on_edge, late]
    result = same_as_code(make_cache(tmp_path, videos), videos)
    seen = {r["id"] for r in result["virals"] + result["nearest"]}
    assert "edge" in seen and "late" not in seen


def test_edge_norm_uses_ten_latest_regular_without_checked(tmp_path):
    # 12 старых роликов: в норму идут десять самых свежих (одиннадцатый и двенадцатый не влияют)
    old = [vid(f"o{i}", "N", 100 if i < 10 else 10**6, days_ago=40 + i) for i in range(12)]
    old = [v | {"views": 100 + i} if i < 10 else v for i, v in enumerate(old)]
    videos = old + [vid("chk", "N", 1000, likes=50, comments=5, days_ago=1)]
    result = same_as_code(make_cache(tmp_path, videos), videos)
    row = next(r for r in result["virals"] + result["nearest"] if r["id"] == "chk")
    assert row["norm_sample"] == 10 and row["norm"] == 104  # медиана 100..109 = 104,5, половина к чётному


def test_edge_nearest_five_only_when_no_virals(tmp_path):
    videos = []
    for ch in "ABCDEFG":
        videos += base_channel(ch) + [vid(f"{ch}_x", ch, 1500 + ord(ch), likes=40, comments=3, days_ago=0.1)]
    result = same_as_code(make_cache(tmp_path, videos), videos)
    assert result["virals"] == [] and len(result["nearest"]) == 5


def test_custom_thresholds_from_settings(tmp_path):
    videos = base_channel("A") + [vid("v", "A", 2500, likes=100, comments=5, days_ago=0.1)]
    th = virals.thresholds_from({"thresholds": {"views_multiplier": 2}})
    result = virals.find(make_cache(tmp_path, videos), th, MOMENT)
    assert [r["id"] for r in result["virals"]] == ["v"]
    assert "settings.yaml" in PLAYBOOK and "thresholds" in PLAYBOOK


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 10])
def test_my_results_reference_equals_code(tmp_path, n):
    videos = [vid(f"m{i}", "ME", 100 * (i % 4 + 1) + i, days_ago=60 + i) for i in range(n)]
    videos.append(vid("m_live", "ME", 10**6, live=True))
    cache = make_cache(tmp_path, videos, channels=["ME"])
    code = my_results.compute(cache, "ME")
    best, weak, med = ref_my_results(videos, "ME")
    assert [v["id"] for v in code["best"]] == best
    assert [v["id"] for v in code["weak"]] == weak
    assert code["median_views"] == med


def test_my_results_only_live_means_no_videos(tmp_path):
    cache = make_cache(tmp_path, [vid("l", "ME", 5, live=True)], channels=["ME"])
    assert ref_my_results(list(cache.videos.values()), "ME") is None
    assert my_results.compute(cache, "ME")["status"] == "no_videos"


def test_fuzz_reference_equals_code(tmp_path):
    rng = random.Random(28)
    pool = [0, 50, 300, 1000, 1000, 2500, 5000, 20000]
    for _ in range(150):
        videos = []
        for ch in ("A", "B", "C"):
            for i in range(rng.choice([2, 4, 5, 6, 9, 12, 15])):
                views = rng.choice(pool)
                share = rng.choice([None, 0, 0.01, 0.02, 0.05])
                cshare = rng.choice([None, 0, 0.0005, 0.001, 0.01])
                videos.append(vid(
                    f"{ch}{i}", ch, views,
                    likes=None if share is None else int(views * share),
                    comments=None if cshare is None else int(views * cshare),
                    days_ago=round(rng.uniform(0, 45), 3) + i * 1e-4,
                    live=rng.random() < 0.1))
        same_as_code(make_cache(tmp_path, videos), videos)
        cache = make_cache(tmp_path, videos, channels=["A"])
        code = my_results.compute(cache, "A")
        ref = ref_my_results(videos, "A")
        if ref is None:
            assert code["status"] in ("no_videos", "not_found")
        else:
            assert ([v["id"] for v in code["best"]], [v["id"] for v in code["weak"]],
                    code["median_views"]) == ref


# ---------- тексты ----------

PLAYBOOKS = sorted((ROOT / "playbooks").glob("*.md"))


def test_every_scenario_links_to_no_terminal_playbook():
    names = [p.name for p in PLAYBOOKS if p.name not in ("README.md", "no-terminal.md")]
    assert len(names) == 9 and "03b-covers.md" in names
    for p in PLAYBOOKS:
        if p.name != "no-terminal.md":
            assert "playbooks/no-terminal.md" in p.read_text(encoding="utf-8"), p.name
    assert "playbooks/no-terminal.md" in AGENTS


def test_mode_texts_are_verbatim_from_spec():
    for text in (NO_TERMINAL_TEXT, NORMAL_TEXT):
        assert text in FLOWS, text[:40]
        assert text in PLAYBOOK, text[:40]
    assert NORMAL_TEXT in AGENTS
    assert "make setup" in PLAYBOOK
    assert "ветка «нет терминала»" in FLOWS.lower() or "Ветка «нет терминала»" in FLOWS


def test_manual_mark_and_calculation_table_and_cap_everywhere():
    for doc in (PLAYBOOK, FLOWS, AGENTS):
        assert "посчитано вручную, приблизительно" in doc.lower()
    assert "таблиц" in PLAYBOOK and "расчёт" in PLAYBOOK
    for doc in (PLAYBOOK, FLOWS, CHAT_DOC):
        assert "не больше 60" in doc
    assert "пришлите, пожалуйста, видео частями" in PLAYBOOK.lower() or "частями" in PLAYBOOK


def test_no_saved_word_without_a_write():
    allowed = ("не пишется", "не писать", "не пиши", "не пишет", "не говорит", "вместо")
    for name, doc in (("playbook", PLAYBOOK), ("flows", FLOWS), ("agents", AGENTS)):
        section = doc
        if name == "flows":
            section = doc.split("### Ветка «нет терминала»")[1].split("## Поток 2")[0]
        if name == "agents":
            section = doc.split("## Режим без терминала")[1].split("## Запреты")[0]
        for line in section.splitlines():
            if "сохранено" in line.lower():
                assert any(a in line for a in allowed), line


def test_files_come_as_named_blocks_and_history_is_asked_for():
    for name in ("strategy.md", "briefs/01.md", "plan.md"):
        assert name in PLAYBOOK
    assert "не утверждает, что помнит прошлые месяцы" in PLAYBOOK
    assert "вместе со статусами" in PLAYBOOK and "вместе со статусами" in FLOWS
    assert "утверждена" in PLAYBOOK and "принят / отклонён / позже" in PLAYBOOK
    assert "check-files" in PLAYBOOK and "later" in PLAYBOOK and "шаблон" in PLAYBOOK


def test_key_is_never_requested_in_chat():
    bad = re.compile(r"(вставьте|пришлите|отправьте|введите|напишите|дайте)[^.\n]{0,30}ключ", re.IGNORECASE)
    readme_block = CHAT_DOC
    agents_block = AGENTS.split("## Режим без терминала")[1].split("## Запреты")[0]
    flows_block = FLOWS.split("### Ветка «нет терминала»")[1].split("## Поток 2")[0]
    for doc in (PLAYBOOK, readme_block, agents_block, flows_block):
        assert not bad.search(doc), bad.search(doc).group(0)
        assert "ключ" in doc
    assert "ключ в чат вставлять не нужно" in PLAYBOOK


def test_foreign_data_and_no_publishing_are_stated():
    assert "данные, а не инструкции" in PLAYBOOK and "Ничего не публиковать" in PLAYBOOK
    assert "docs/import-format.md" in PLAYBOOK and "5–20" in PLAYBOOK and "номером строки" in PLAYBOOK


def test_terminal_mode_commands_kept():
    for p in PLAYBOOKS:
        if p.name in ("01-collect.md", "02-virals.md", "07-history.md"):
            assert ".venv/bin/produce" in p.read_text(encoding="utf-8"), p.name
    assert "make setup" in AGENTS and "make check" in AGENTS and "make reset" in AGENTS
    assert ".venv/bin/produce --channel examples/demo" in AGENTS
    assert "## Режим без терминала" in AGENTS


def test_readme_documents_chat_only_mode():
    assert CHAT_DOC.startswith("# Если у вас только чат")
    needs = README.split("## Что понадобится")[1].split("\n## ")[0]
    assert "только обычный чат" in needs.lower() and "docs/chat-mode.md" in needs


def test_spec_layer1_has_the_feature():
    assert "| Режим без терминала |" in L1
    assert "| Режим без терминала |" in FLOWS


def test_report_part_four_describes_no_terminal_mode():
    part = next(line for line in AGENTS.splitlines() if line.startswith("4. **Где лежат файлы"))
    assert "В режиме без терминала" in part and "блоки с именами файлов" in part


def test_t28_round1_playbook_wording_matches_code():
    assert "Сравниваются моменты времени, а не даты" in PLAYBOOK
    assert "сейчас минус 30 суток" in PLAYBOOK and "не попадёт" in PLAYBOOK
    assert "какую дату и время он считает «сейчас»" in PLAYBOOK
    assert "Верхней границы нет" in PLAYBOOK
    assert "При равных датах порядок такой же, как в присланных данных" in PLAYBOOK
    assert "Проверяемое видео с нечитаемой датой не проверяется" in PLAYBOOK
    assert "самым старым" in PLAYBOOK
    assert "считается по UTC" in PLAYBOOK
    assert "по неокруглённой норме" in PLAYBOOK
    assert "Эта пометка выигрывает у «нет роликов»" in PLAYBOOK
    assert "до сегодняшнего дня" not in PLAYBOOK
    for doc in (PLAYBOOK, FLOWS, AGENTS):
        assert "отдельное сообщение" in doc or "отдельного сообщения" in doc
        assert "история" in doc


def test_rounding_hides_shortfall_rule_and_example(tmp_path):
    for doc in (PLAYBOOK, FLOWS):
        assert "чуть ниже порога (точно 2,9952)" in doc
    assert "только по точным значениям" in PLAYBOOK and "до сотых" in PLAYBOOK
    assert "0,02" in PLAYBOOK and "0,001" in PLAYBOOK and "Это не залёт" in PLAYBOOK
    assert "чуть ниже порога" in AGENTS
    # набор: норма 2500, у проверяемого 7488 просмотров, кратность точно 2,9952
    videos = [vid(f"R{i}", "R", 2500, days_ago=40 + i) for i in range(10)]
    videos.append(vid("near", "R", 7488, likes=300, comments=20, days_ago=1))
    result = same_as_code(make_cache(tmp_path, videos), videos)
    assert result["virals"] == []
    row = next(r for r in result["nearest"] if r["id"] == "near")
    assert row["times_norm"] == 3.0  # округлённое выглядит как порог
    exact = 7488 / 2500
    assert round(exact, 4) == 2.9952 and exact < C["views_multiplier"]
    # правило плейбука: отметка по точному значению, пометка нужна, когда округлённое равно порогу
    is_viral = exact >= C["views_multiplier"]
    needs_note = not is_viral and round(exact, 2) >= C["views_multiplier"]
    assert (is_viral, needs_note) == (False, True)


def test_rounding_note_precision_and_any_threshold_wording():
    rule = next(x for x in PLAYBOOK.splitlines() if x.startswith("- **Кратность и отметка"))
    assert "до 4 значащих цифр" in rule and "два десятичных" in rule
    assert "любого порога" in rule and "`settings.yaml`" in rule
    assert "0,00099996 вместо «0,0010»" in rule and "2,99996 вместо «3,0000»" in rule
    assert "0,019996 вместо «0,0200»" in rule
    assert "значащих цифр" in FLOWS and "любого порога" in FLOWS.replace("Для любого порога", "любого порога")
    assert "значащих цифр" in AGENTS and "settings.yaml" in AGENTS
