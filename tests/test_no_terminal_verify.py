"""T28, независимая сверка (тестировщик): эталон написан заново по тексту playbooks/no-terminal.md.

Не использует хелперы tests/test_no_terminal.py. Сравнивает с virals.find и my_results.compute.
"""

import random
import re
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path

import pytest

from produce.core import my_results, virals
from produce.core.collect import Cache

ROOT = Path(__file__).parent.parent
NOW = datetime(2026, 11, 3, tzinfo=UTC)


def stamp(days_ago, hours=0):
    return (NOW - timedelta(days=days_ago, hours=hours)).isoformat().replace("+00:00", "Z")


def v(i, ch, views, days_ago, likes=None, comments=None, live=False, pub=None):
    return {"id": i, "title": i, "channel_id": ch, "published_at": pub or stamp(days_ago),
            "views": views, "likes": likes, "comments": comments, "is_live": live}


def cache_of(tmp_path, videos):
    c = Cache(tmp_path)
    c.videos = {x["id"]: x for x in videos}
    c.channels = {x["channel_id"]: {"title": x["channel_id"]} for x in videos}
    return c


# ---- эталон строго по словам плейбука ----

def med(values):
    s = sorted(values)
    n = len(s)
    return Fraction(s[n // 2]) if n % 2 else Fraction(s[n // 2 - 1] + s[n // 2], 2)


def py_round_half_even(fr):
    return round(fr)  # Fraction.round -> half to even


def ref(videos):
    ordinary = [x for x in videos if not x["is_live"] and x["views"] is not None]
    border = NOW - timedelta(days=30)
    checked = [x for x in ordinary if border <= datetime.fromisoformat(x["published_at"])]
    virals_, rows, skipped = [], [], []
    for x in checked:
        same = [y for y in ordinary if y["channel_id"] == x["channel_id"]]
        if len(same) < 5:
            skipped.append(x["id"])
            continue
        rest = sorted((y for y in same if y["id"] != x["id"]),
                      key=lambda y: datetime.fromisoformat(y["published_at"]),
                      reverse=True)[:10]
        norm = med([y["views"] for y in rest])
        mult = Fraction(x["views"]) / norm if norm > 0 else None
        lr = Fraction(x["likes"], x["views"]) if x["likes"] is not None and x["views"] > 0 else None
        cr = Fraction(x["comments"], x["views"]) if x["comments"] is not None and x["views"] > 0 else None
        ok = (mult is not None and mult >= 3 and lr is not None and lr >= Fraction(2, 100)
              and cr is not None and cr >= Fraction(1, 1000))
        close = min(
            min(mult / 3, 1) if mult is not None else Fraction(0),
            min(lr / Fraction(2, 100), 1) if lr is not None else Fraction(0),
            min(cr / Fraction(1, 1000), 1) if cr is not None else Fraction(0))
        rows.append({"id": x["id"], "norm": py_round_half_even(norm),
                     "mult": round(float(mult), 2) if mult is not None else None,
                     "ok": ok, "close": close})
    virals_ = sorted((r for r in rows if r["ok"]), key=lambda r: (-r["mult"], r["id"]))
    rest = sorted((r for r in rows if not r["ok"]), key=lambda r: (-r["close"], r["id"]))
    return virals_, ([] if virals_ else rest[:5]), sorted(skipped)


def ref_mine(videos, ch):
    mine = [x for x in videos if x["channel_id"] == ch and not x["is_live"] and x["views"] is not None]
    mine.sort(key=lambda x: (-x["views"], x["id"]))
    n = len(mine)
    best_n = min(3, (n + 1) // 2)
    weak_n = min(3, n - best_n)
    best = [x["id"] for x in mine[:best_n]]
    weak = [x["id"] for x in reversed(mine)][:weak_n]
    return best, weak, round(med([x["views"] for x in mine]))


def check(tmp_path, videos):
    c = cache_of(tmp_path, videos)
    res = virals.find(c, virals.thresholds_from({}), NOW)
    rv, rn, rs = ref(videos)
    assert [r["id"] for r in res["virals"]] == [r["id"] for r in rv]
    assert [r["times_norm"] for r in res["virals"]] == [r["mult"] for r in rv]
    assert [r["norm"] for r in res["virals"]] == [r["norm"] for r in rv]
    assert [r["id"] for r in res["nearest"]] == [r["id"] for r in rn]
    assert sorted(s["id"] for s in res["skipped"]) == rs
    return res


def regular_channel(ch, n=6, views=100, start=40):
    return [v(f"{ch}{i}", ch, views, start + i * 2, 5, 1) for i in range(n)]


def test_my_results_sizes_1_to_9(tmp_path):
    for n in range(1, 10):
        vids = [v(f"m{i}", "ME", (i * 37) % 11 * 10 + i, 3 + i) for i in range(n)]
        code = my_results.compute(cache_of(tmp_path, vids), "ME", source="import")
        best, weak, median_ = ref_mine(vids, "ME")
        assert [x["id"] for x in code["best"]] == best, n
        assert [x["id"] for x in code["weak"]] == weak, n
        assert code["median_views"] == median_, n


def test_my_results_best_weak_counts_table():
    expected = {1: (1, 0), 2: (1, 1), 3: (2, 1), 4: (2, 2), 5: (3, 2), 6: (3, 3), 7: (3, 3)}
    for n, (b, w) in expected.items():
        assert (min(3, (n + 1) // 2), min(3, n - min(3, (n + 1) // 2))) == (b, w)


def test_my_results_median_halves_round_even(tmp_path):
    vids = [v("a", "ME", 103, 1), v("b", "ME", 106, 2)]  # 104.5 -> 104
    assert my_results.compute(cache_of(tmp_path, vids), "ME")["median_views"] == 104
    vids = [v("a", "ME", 104, 1), v("b", "ME", 107, 2)]  # 105.5 -> 106
    assert my_results.compute(cache_of(tmp_path, vids), "ME")["median_views"] == 106


def test_my_results_ties_and_live_and_foreign(tmp_path):
    vids = [v("b", "ME", 10, 1), v("a", "ME", 10, 2), v("c", "ME", 10, 3), v("l", "ME", 999, 1, live=True),
            v("x", "OTHER", 5000, 1)]
    code = my_results.compute(cache_of(tmp_path, vids), "ME")
    assert [x["id"] for x in code["best"]] == ["a", "b"]
    assert [x["id"] for x in code["weak"]] == ["c"]
    assert code["videos"] == 3


def test_my_results_statuses(tmp_path):
    c = cache_of(tmp_path, [v("a", "X", 1, 1)])
    assert my_results.compute(c, None)["note"] == "Мой канал не задан, пропускаю"
    assert my_results.compute(c, "ME", source="import")["note"] == "Моего канала нет в файле импорта, пропускаю"
    c.channels["ME"] = {"title": "me"}
    assert my_results.compute(c, "ME")["note"] == "У моего канала нет роликов с открытой статистикой, пропускаю"


def test_boundary_30_days_exact(tmp_path):
    vids = regular_channel("A") + [v("edge", "A", 1000, 30, 50, 5), v("old", "A", 1000, 30, 50, 5, pub=stamp(30, 1)),
                                  v("in", "A", 1000, 29, 50, 5)]
    res = check(tmp_path, vids)
    ids = [r["id"] for r in res["virals"]]
    assert "edge" in ids and "in" in ids and "old" not in ids


def test_exactly_5_and_4(tmp_path):
    five = regular_channel("A", 5, start=2)
    four = regular_channel("B", 4, start=2)
    res = check(tmp_path, five + four)
    assert {s["id"] for s in res["skipped"]} == {v_["id"] for v_ in four}


def test_live_makes_channel_short(tmp_path):
    vids = regular_channel("A", 4, start=2) + [v("live", "A", 5, 3, live=True)]
    res = check(tmp_path, vids)
    assert len(res["skipped"]) == 4


def test_views_none_not_ordinary(tmp_path):
    vids = regular_channel("A", 4, start=2) + [v("nv", "A", None, 3)]
    check(tmp_path, vids)


def test_unknown_likes_comments_never_viral(tmp_path):
    base = regular_channel("A")
    vids = base + [v("nl", "A", 9999, 1, None, 99), v("nc", "A", 9999, 1, 999, None), v("ok", "A", 9999, 1, 999, 99)]
    res = check(tmp_path, vids)
    assert [r["id"] for r in res["virals"]] == ["ok"]


def test_zero_norm_and_zero_views(tmp_path):
    vids = [v(f"z{i}", "Z", 0, 10 + i, 0, 0) for i in range(6)] + [v("big", "Z", 500, 1, 100, 10),
                                                                   v("zero", "Z", 0, 1, 0, 0)]
    res = check(tmp_path, vids)
    assert res["virals"] == []


def test_threshold_exact_values_are_inclusive(tmp_path):
    # норма 100: views 300 ровно 3x, likes 6 = 0.02, comments 0.3 -> нужно views>=1000 для 0.001
    vids = regular_channel("A", 6, 100) + [v("t", "A", 3000, 1, 60, 3)]
    res = check(tmp_path, vids)
    assert [r["id"] for r in res["virals"]] == ["t"]
    vids = regular_channel("A", 6, 100) + [v("t", "A", 3000, 1, 59, 3)]
    assert check(tmp_path, vids)["virals"] == []


def test_equal_dates_all_equal_views(tmp_path):
    same = stamp(5)
    vids = [v(f"e{i}", "E", 100, 0, 5, 1, pub=same) for i in range(8)] + [v("hit", "E", 5000, 1, 500, 50)]
    check(tmp_path, vids)


def test_other_channels_do_not_leak_into_norm(tmp_path):
    vids = regular_channel("A") + regular_channel("B", 6, 1_000_000) + [v("hit", "A", 400, 1, 40, 4)]
    res = check(tmp_path, vids)
    assert [r["id"] for r in res["virals"]] == ["hit"]


def test_norm_uses_only_last_10(tmp_path):
    old = [v(f"o{i}", "A", 1_000_000, 100 + i, 5, 1) for i in range(10)]
    vids = regular_channel("A", 10, 100, start=35) + old + [v("hit", "A", 400, 1, 40, 4)]
    res = check(tmp_path, vids)
    assert res["virals"][0]["norm"] == 100


def test_rounding_ties_in_virals_order(tmp_path):
    vids = regular_channel("A", 6, 100) + [v("b", "A", 4000, 1, 400, 40), v("a", "A", 4000, 1, 400, 40)]
    res = check(tmp_path, vids)
    assert [r["id"] for r in res["virals"]] == ["a", "b"]


def test_timezone_offsets_boundary(tmp_path):
    # 2026-10-04T00:00+03:00 = 2026-10-03T21:00Z, раньше границы (2026-10-04T00:00Z) -> не входит
    vids = regular_channel("A") + [v("tz", "A", 1000, 0, 100, 10, pub="2026-10-04T00:00:00+03:00")]
    res = virals.find(cache_of(tmp_path, vids), virals.thresholds_from({}), NOW)
    assert "tz" not in [r["id"] for r in res["virals"]]


@pytest.mark.parametrize("seed", range(300))
def test_random_sets(tmp_path, seed):
    rnd = random.Random(seed)
    vids, n = [], 0
    for ch in "ABCD":
        for _ in range(rnd.choice([3, 4, 5, 5, 6, 9, 12, 15])):
            n += 1
            live = rnd.random() < 0.08
            views = rnd.choice([0, 1, 50, 100, 100, 120, 300, 5000, 90000])
            vids.append(v(f"v{n}", ch, views, rnd.choice([0, 1, 5, 29, 30, 31, 45, 80]),
                          rnd.choice([None, 0, views // 40, views // 10]),
                          rnd.choice([None, 0, views // 900, views // 50]), live))
    # даты уникальны в пределах канала: сдвиг на n минут, чтобы порядок выборки был однозначен
    for i, x in enumerate(vids):
        d = datetime.fromisoformat(x["published_at"]) - timedelta(minutes=i)
        x["published_at"] = d.isoformat().replace("+00:00", "Z")
    check(tmp_path, vids)
    mine = ref_mine(vids, "A") if any(x["channel_id"] == "A" and not x["is_live"] for x in vids) else None
    if mine:
        code = my_results.compute(cache_of(tmp_path, vids), "A", source="import")
        assert ([x["id"] for x in code["best"]], [x["id"] for x in code["weak"]],
                code["median_views"]) == mine


def test_demo_data_via_reference(tmp_path):
    import csv
    rows = list(csv.DictReader((ROOT / "examples/demo/import.csv").open(encoding="utf-8")))
    def num(s):
        return int(s) if s not in (None, "") else None
    vids = [{"id": r["id"], "title": r["title"], "channel_id": r["channel_id"],
             "published_at": r["published_at"] if "T" in r["published_at"] else r["published_at"] + "T00:00:00+00:00",
             "views": num(r["views"]), "likes": num(r.get("likes")), "comments": num(r.get("comments")),
             "is_live": (r.get("is_live") or "").strip().lower() in ("да", "true", "1")} for r in rows]
    moment_vids = vids
    c = cache_of(tmp_path, moment_vids)
    res = virals.find(c, virals.thresholds_from({}), datetime(2026, 10, 27, tzinfo=UTC))
    global NOW
    saved, NOW = NOW, datetime(2026, 10, 27, tzinfo=UTC)
    try:
        rv, rn, rs = ref(moment_vids)
    finally:
        NOW = saved
    assert [r["id"] for r in res["virals"]] == [r["id"] for r in rv]
    assert [r["id"] for r in res["nearest"]] == [r["id"] for r in rn]
    assert sorted(s["id"] for s in res["skipped"]) == rs
    assert re.match(r"demo", rv[0]["id"]) if rv else True
