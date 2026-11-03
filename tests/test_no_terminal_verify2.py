"""T28, круг 2 (тестировщик): эталон строго по новому тексту playbooks/no-terminal.md.

Новое в тексте: граница по моментам «сейчас минус 30 суток», дата без времени = 00:00, без пояса = UTC,
верхней границы нет, равные даты = порядок данных, нечитаемая дата (проверяемое пропускается, в норме
самый старый), кратность по неокруглённой норме, «нет в файле» важнее «нет роликов».
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
PLAYBOOK = (ROOT / "playbooks" / "no-terminal.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
FLOWS = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")


def parse(text):
    """Дата по плейбуку: без времени = 00:00, без пояса = UTC, нечитаемая = None."""
    try:
        m = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return m if m.tzinfo else m.replace(tzinfo=UTC)


def v(i, ch, views, pub, likes=None, comments=None, live=False):
    return {"id": i, "title": i, "channel_id": ch, "published_at": pub,
            "views": views, "likes": likes, "comments": comments, "is_live": live}


def cache_of(tmp_path, videos, channels=None):
    c = Cache(tmp_path)
    c.videos = {x["id"]: x for x in videos}
    c.channels = channels if channels is not None else {x["channel_id"]: {"title": x["channel_id"]} for x in videos}
    return c


def med(values):
    s = sorted(values)
    n = len(s)
    return Fraction(s[n // 2]) if n % 2 else Fraction(s[n - 1 - n // 2 + 0] + s[n // 2], 2)


def ref(videos, now):
    ordinary = [x for x in videos if not x["is_live"] and x["views"] is not None]
    border = now - timedelta(days=30)
    rows, skipped = [], []
    for x in ordinary:
        p = parse(x["published_at"])
        if p is None or p < border:
            continue
        same = [y for y in ordinary if y["channel_id"] == x["channel_id"]]
        if len(same) < 5:
            skipped.append(x["id"])
            continue
        old = datetime.min.replace(tzinfo=UTC)
        rest = sorted((y for y in same if y["id"] != x["id"]),
                      key=lambda y: parse(y["published_at"]) or old, reverse=True)[:10]  # стабильно: порядок данных
        norm = med([y["views"] for y in rest])
        mult = Fraction(x["views"]) / norm if norm > 0 else None
        lr = Fraction(x["likes"], x["views"]) if x["likes"] is not None and x["views"] > 0 else None
        cr = Fraction(x["comments"], x["views"]) if x["comments"] is not None and x["views"] > 0 else None
        ok = (mult is not None and mult >= 3 and lr is not None and lr >= Fraction(2, 100)
              and cr is not None and cr >= Fraction(1, 1000))
        close = min(min(mult / 3, 1) if mult is not None else Fraction(0),
                    min(lr / Fraction(2, 100), 1) if lr is not None else Fraction(0),
                    min(cr / Fraction(1, 1000), 1) if cr is not None else Fraction(0))
        rows.append({"id": x["id"], "norm": round(norm), "mult": round(float(mult), 2) if mult is not None else None,
                     "ok": ok, "close": close})
    vir = sorted((r for r in rows if r["ok"]), key=lambda r: (-r["mult"], r["id"]))
    oth = sorted((r for r in rows if not r["ok"]), key=lambda r: (-r["close"], r["id"]))
    return vir, ([] if vir else oth[:5]), sorted(skipped)


def check(tmp_path, videos, now):
    res = virals.find(cache_of(tmp_path, videos), virals.thresholds_from({}), now)
    rv, rn, rs = ref(videos, now)
    assert [r["id"] for r in res["virals"]] == [r["id"] for r in rv]
    assert [(r["norm"], r["times_norm"]) for r in res["virals"]] == [(r["norm"], r["mult"]) for r in rv]
    assert [r["id"] for r in res["nearest"]] == [r["id"] for r in rn]
    assert sorted(s["id"] for s in res["skipped"]) == rs
    return res


def regular(ch, n=6, views=100):
    return [v(f"{ch}{i}", ch, views, f"2026-09-{10 + i:02d}", 5, 1) for i in range(n)]


NOW_MIDNIGHT = datetime(2026, 11, 3, 0, 0, tzinfo=UTC)
NOW_AFTERNOON = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize("now,expected_in", [(NOW_MIDNIGHT, True), (NOW_AFTERNOON, False)])
def test_border_date_only(tmp_path, now, expected_in):
    # дата без времени ровно 30 суток назад: в 00:00 входит, днём нет
    vids = regular("A") + [v("edge", "A", 1000, "2026-10-04", 50, 5)]
    res = check(tmp_path, vids, now)
    assert ("edge" in [r["id"] for r in res["virals"]]) is expected_in


def test_border_with_time_and_zone(tmp_path):
    vids = regular("A") + [
        v("on", "A", 1000, "2026-10-04T14:00:00Z", 50, 5),
        v("before", "A", 1000, "2026-10-04T13:59:59Z", 50, 5),
        v("naive_on", "A", 1000, "2026-10-04T14:00:00", 50, 5),
        v("plus3_on", "A", 1000, "2026-10-04T17:00:00+03:00", 50, 5),
        v("plus3_before", "A", 1000, "2026-10-04T16:59:59+03:00", 50, 5)]
    res = check(tmp_path, vids, NOW_AFTERNOON)
    ids = {r["id"] for r in res["virals"]}
    assert ids == {"on", "naive_on", "plus3_on"}


def test_future_date_is_checked(tmp_path):
    vids = regular("A") + [v("fut", "A", 1000, "2027-01-01", 50, 5)]
    res = check(tmp_path, vids, NOW_AFTERNOON)
    assert "fut" in [r["id"] for r in res["virals"]]


def test_unreadable_date_checked_is_skipped(tmp_path):
    vids = regular("A") + [v("bad", "A", 1000, "вчера", 50, 5), v("empty", "A", 1000, "", 50, 5)]
    res = check(tmp_path, vids, NOW_AFTERNOON)
    assert res["virals"] == []
    assert "bad" not in {s["id"] for s in res["skipped"]}


def test_unreadable_date_in_pool_is_oldest(tmp_path):
    # 10 нормальных роликов по 100, один нечитаемый с огромными просмотрами: он 11-й и в норму не попадает
    vids = regular("A", 10) + [v("bad", "A", 10_000_000, "нет", 5, 1), v("hit", "A", 400, "2026-11-01", 40, 4)]
    res = check(tmp_path, vids, NOW_AFTERNOON)
    assert res["virals"][0]["norm"] == 100
    # если нормальных меньше 10, нечитаемый берётся последним
    vids = regular("A", 6) + [v("bad", "A", 10_000_000, "нет", 5, 1), v("hit", "A", 400, "2026-11-01", 40, 4)]
    check(tmp_path, vids, NOW_AFTERNOON)


@pytest.mark.parametrize("seed", range(20))
def test_equal_dates_follow_data_order(tmp_path, seed):
    rnd = random.Random(seed)
    same = [v(f"e{i}", "E", rnd.choice([10, 100, 1000, 5000]), "2026-10-20", 5, 1) for i in range(14)]
    hit = v("hit", "E", 3000, "2026-11-01", 300, 30)
    rnd.shuffle(same)
    check(tmp_path, same + [hit], NOW_AFTERNOON)
    rnd.shuffle(same)
    check(tmp_path, [hit] + same, NOW_AFTERNOON)


def test_equal_dates_order_changes_result(tmp_path):
    # плейбук прямо говорит, что от порядка зависит; докажем, что это правда и код следует порядку данных
    small = [v(f"s{i}", "E", 100, "2026-10-20", 5, 1) for i in range(6)]
    big = [v(f"g{i}", "E", 9000, "2026-10-20", 5, 1) for i in range(5)]
    hit = v("hit", "E", 20000, "2026-11-01", 2000, 200)
    r1 = check(tmp_path, small + big + [hit], NOW_AFTERNOON)
    r2 = check(tmp_path, big + small + [hit], NOW_AFTERNOON)
    assert r1["virals"][0]["norm"] != r2["virals"][0]["norm"]


def test_multiplier_on_unrounded_norm(tmp_path):
    # норма 104.5 (показывается 104). 313.5 -> кратность ровно 3 по точной норме; views целые: 314 даёт >=3,
    # 313 даёт 2.995 (<3), хотя по округлённой 104 было бы 313/104 = 3.009 (>=3)
    base = [v(f"b{i}", "N", 103 if i % 2 else 106, f"2026-09-{10 + i:02d}", 9, 1) for i in range(4)]
    for views, expect in [(313, False), (314, True)]:
        vids = base + [v("t", "N", views, "2026-11-01", views, views)]
        res = check(tmp_path, vids, NOW_AFTERNOON)
        assert (bool(res["virals"])) is expect, views
        if not expect:
            near = res["nearest"][0]
            assert near["norm"] == 104 and near["times_norm"] == 3.0  # 2.9952 в таблице выглядит как ×3, но залётом не является


def test_live_only_my_channel(tmp_path):
    live = [v("l1", "ME", 500, "2026-10-30", live=True)]
    # канала нет в channels -> «нет в файле» (важнее «нет роликов»)
    c = cache_of(tmp_path, live, channels={})
    assert my_results.compute(c, "ME", source="import")["status"] == "not_found"
    # канал в channels есть -> «нет роликов с открытой статистикой»
    c = cache_of(tmp_path, live, channels={"ME": {"title": "me"}})
    assert my_results.compute(c, "ME", source="import")["status"] == "no_videos"
    # канала нет вообще и видео нет
    c = cache_of(tmp_path, [v("x", "Z", 1, "2026-10-30")], channels={})
    assert my_results.compute(c, "ME", source="import")["status"] == "not_found"
    # ролик без просмотров
    c = cache_of(tmp_path, [v("n", "ME", None, "2026-10-30")], channels={"ME": {"title": "me"}})
    assert my_results.compute(c, "ME")["status"] == "no_videos"


def test_my_results_ignores_window(tmp_path):
    vids = [v("old", "ME", 10, "2020-01-01"), v("fut", "ME", 20, "2030-01-01"), v("bad", "ME", 30, "нет")]
    res = my_results.compute(cache_of(tmp_path, vids), "ME", source="import")
    assert res["videos"] == 3


def _gen(rnd):
    pubs = ["2026-10-04", "2026-10-03", "2026-10-05", "2026-10-04T14:00:00Z", "2026-10-04T13:59:59Z",
            "2026-10-04T14:00:00", "2026-11-03", "2027-02-01", "2026-09-01", "2026-10-20", "нет", "",
            "2026-10-04T17:00:00+03:00", "2026-10-20T10:00:00Z"]
    vids, n = [], 0
    for ch in "ABC":
        for _ in range(rnd.choice([4, 5, 6, 8, 12, 14])):
            n += 1
            views = rnd.choice([0, 100, 100, 104, 106, 300, 313, 314, 5000])
            vids.append(v(f"v{n}", ch, views, rnd.choice(pubs),
                          rnd.choice([None, 0, views // 40, views // 10]),
                          rnd.choice([None, 0, views // 900, views // 50]), rnd.random() < 0.08))
    rnd.shuffle(vids)
    return vids


@pytest.mark.parametrize("seed", range(400))
def test_random_hostile(tmp_path, seed):
    rnd = random.Random(1000 + seed)
    vids = _gen(rnd)
    now = rnd.choice([NOW_MIDNIGHT, NOW_AFTERNOON, datetime(2026, 11, 3, 14, 0, 1, tzinfo=UTC)])
    check(tmp_path, vids, now)
    for ch in "ABC":
        mine = [x for x in vids if x["channel_id"] == ch and not x["is_live"] and x["views"] is not None]
        if not mine:
            continue
        code = my_results.compute(cache_of(tmp_path, vids), ch, source="import")
        mine.sort(key=lambda x: (-x["views"], x["id"]))
        n = len(mine)
        b = min(3, (n + 1) // 2)
        w = min(3, n - b)
        assert [x["id"] for x in code["best"]] == [x["id"] for x in mine[:b]]
        assert [x["id"] for x in code["weak"]] == [x["id"] for x in reversed(mine)][:w]
        assert code["median_views"] == round(med([x["views"] for x in mine]))


def test_demo_two_launch_times(tmp_path):
    import csv
    rows = list(csv.DictReader((ROOT / "examples/demo/import.csv").open(encoding="utf-8")))

    def num(s):
        return int(s) if s not in (None, "") else None
    vids = [{"id": r["id"], "title": r["title"], "channel_id": r["channel_id"], "published_at": r["published_at"],
             "views": num(r["views"]), "likes": num(r.get("likes")), "comments": num(r.get("comments")),
             "is_live": (r.get("is_live") or "").strip().lower() in ("да", "true", "1")} for r in rows]
    for now in (datetime(2026, 10, 27, tzinfo=UTC), datetime(2026, 10, 27, 14, tzinfo=UTC),
                datetime(2026, 11, 3, tzinfo=UTC)):
        check(tmp_path, vids, now)


# ---- согласованность текстов ----

def test_playbook_not_self_contradicting():
    assert "до сегодняшнего дня" not in PLAYBOOK
    assert "граница входит" not in PLAYBOOK  # старая формулировка «по дате»
    assert "Верхней границы нет" in PLAYBOOK
    # единое правило границы: везде моменты
    assert len(re.findall(r"30 суток", PLAYBOOK)) >= 2


def test_approval_rule_same_everywhere():
    for name, text in (("playbook", PLAYBOOK), ("agents", AGENTS), ("flows", FLOWS)):
        low = text.lower()
        assert re.search(r"отдельн\w+ сообщени", low), name
        assert "история" in low and "утверждена" in low, name
    assert "отдельное сообщение самого человека" in PLAYBOOK
    assert "Статус: утверждена" in PLAYBOOK


def test_ordinary_mode_approval_rule_not_weakened():
    # обычный режим: статус ставит человек правкой файла; плейбук прямо называет отличие
    assert "отличие от обычного режима" in PLAYBOOK and "правкой файла" in PLAYBOOK
    p5 = (ROOT / "playbooks/05-strategy.md").read_text(encoding="utf-8")
    assert "Утверждена" in p5 or "утверждена" in p5
    assert "no-terminal.md" in (ROOT / "playbooks/00-month.md").read_text(encoding="utf-8")
