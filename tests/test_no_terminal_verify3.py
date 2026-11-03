"""T28, узкая проверка правки «×3» (тестировщик): эталон показа расчёта по тексту playbooks/no-terminal.md.

Эталон: точное сравнение на Fraction; пометка «чуть ниже порога» нужна, когда округлённое значение
выглядит не ниже порога, а точное ниже. Сверка «Залёт?» с virals.find и поиск дыр правила.
Бывшие xfail(strict) (дыры текста) сняты после правки правила: тесты теперь зелёные и держат формулировку.
"""

import random
import re
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from produce.core import virals
from produce.core.collect import Cache, now

ROOT = Path(__file__).parent.parent
PLAYBOOK = (ROOT / "playbooks" / "no-terminal.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
FLOWS = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")


def shown(x: Fraction, digits: int) -> Decimal:
    """Округление до digits знаков (половина вверх, как человек)."""
    q = Decimal(1).scaleb(-digits)
    return (Decimal(x.numerator) / Decimal(x.denominator)).quantize(q, rounding=ROUND_HALF_UP)


def needs_note(exact: Fraction, thr: Fraction, digits: int) -> bool:
    """Правило: округление скрывает недобор = выглядит не ниже порога, а точно ниже."""
    return exact < thr and Decimal(shown(exact, digits)) >= Decimal(thr.numerator) / Decimal(thr.denominator)


def make_cache(tmp_path, views, likes, comments, th_norm=1000, ):
    videos = [{"id": f"R{i}", "title": "r", "channel_id": "C", "views": th_norm,
               "published_at": (now() - timedelta(days=40 + i)).isoformat(), "is_live": False}
              for i in range(10)]
    videos.append({"id": "T", "title": "t", "channel_id": "C", "views": views, "likes": likes,
                   "comments": comments, "is_live": False,
                   "published_at": (now() - timedelta(days=1)).isoformat()})
    c = Cache(tmp_path)
    c.videos = {x["id"]: x for x in videos}
    c.channels = {"C": {"title": "C"}}
    return c


def th(mult=3, lr=0.02, cr=0.001):
    return virals.Thresholds(mult, lr, cr, 10, 5)


MULT_CASES = [  # (норма, просмотры, точная кратность, ожидаем залёт по кратности, нужна пометка)
    (2500, 7488, "2.9952"), (2000, 5990, "2.995"), (10000, 29949, "2.9949"),
    (10000, 29951, "2.9951"), (1000, 3000, "3"), (10000, 30049, "3.0049"),
    (10000, 29500, "2.95"), (10000, 29999, "2.9999"),
]


@pytest.mark.parametrize("norm,views,_", MULT_CASES)
def test_viral_flag_matches_code_and_note_rule_for_multiplier(tmp_path, norm, views, _):
    exact = Fraction(views, norm)
    cache = make_cache(tmp_path, views, likes=views, comments=views, th_norm=norm)  # лайки/комменты с запасом
    result = virals.find(cache, th())
    is_viral = any(r["id"] == "T" for r in result["virals"])
    assert is_viral == (exact >= 3)  # «Залёт?» по точному значению
    rec = next(r for r in result["virals"] + result["nearest"] + result.get("others", []) if r["id"] == "T") \
        if (result["virals"] or result["nearest"]) else None
    if rec is not None:
        assert rec["times_norm"] == float(shown(exact, 2))
    note = needs_note(exact, Fraction(3), 2)
    # Пометка нужна ровно для [2,995; 3)
    assert note == (Fraction(2995, 1000) <= exact < 3)
    if is_viral:
        assert not note


def test_note_window_for_multiplier_is_only_hidden_shortfall():
    for num in range(29000, 30100):
        exact = Fraction(num, 10000)
        assert needs_note(exact, Fraction(3), 2) == (Fraction(2995, 1000) <= exact < 3)


def test_custom_thresholds_hidden_shortfall_symmetry(tmp_path):
    rnd = random.Random(28)
    for _ in range(200):
        mult = rnd.choice([1.5, 2, 2.5, 4, 5, 10])
        norm = rnd.choice([1000, 2500, 7000])
        base = Fraction(str(mult))
        views = int(base * norm) + rnd.randint(-8, 8)
        if views <= 0:
            continue
        cache = make_cache(tmp_path, views, likes=views, comments=views, th_norm=norm)
        res = virals.find(cache, th(mult=mult))
        is_viral = any(r["id"] == "T" for r in res["virals"])
        exact = Fraction(views, norm)
        assert is_viral == (exact >= base)
        if needs_note(exact, base, 2):
            assert not is_viral  # пометка и «да» не сочетаются


@pytest.mark.parametrize("likes,views,expect_viral", [
    (19996, 1_000_000, False), (20000, 1_000_000, True), (199, 10_000, False), (200, 10_000, True),
])
def test_likes_boundary_matches_code(tmp_path, likes, views, expect_viral):
    cache = make_cache(tmp_path, views, likes=likes, comments=views, th_norm=views // 4)
    res = virals.find(cache, th())
    assert any(r["id"] == "T" for r in res["virals"]) == expect_viral
    exact = Fraction(likes, views)
    if exact < Fraction(2, 100):
        assert needs_note(exact, Fraction(2, 100), 2) == (exact >= Fraction(15, 1000))


@pytest.mark.parametrize("comments,views,expect_viral", [
    (999, 1_000_000, False), (1000, 1_000_000, True), (99996, 100_000_000, False),
])
def test_comments_boundary_matches_code(tmp_path, comments, views, expect_viral):
    cache = make_cache(tmp_path, views, likes=views, comments=comments, th_norm=views // 4)
    res = virals.find(cache, th())
    assert any(r["id"] == "T" for r in res["virals"]) == expect_viral


def test_two_digits_makes_comments_ratio_meaningless():
    """Факт: комментарии ÷ просмотры при двух знаках: порог 0,001 это «0,00». Правило не должно
    требовать для порога 0,001 именно две цифры."""
    assert shown(Fraction(1, 1000), 2) == Decimal("0.00")
    assert shown(Fraction(99996, 100_000_000), 2) == Decimal("0.00")  # недобор не «скрыт», но и число пустое
    # при двух знаках для лайков порог 0,02 сохраняет смысл
    assert shown(Fraction(199, 10000), 2) == Decimal("0.02") and needs_note(Fraction(199, 10000), Fraction(2, 100), 2)


def rule_line():
    return next(x for x in PLAYBOOK.splitlines() if x.startswith("- **Кратность и отметка"))


def test_all_three_documents_carry_the_rule():
    assert "чуть ниже порога (точно 2,9952)" in rule_line()
    assert "чуть ниже порога (точно 2,9952)" in AGENTS and "чуть ниже порога (точно 2,9952)" in FLOWS
    for doc in (PLAYBOOK, FLOWS):
        assert "только по точным значениям" in doc
        assert "до 4 знаков" in doc
    assert "0,02" in rule_line() and "0,001" in rule_line()


def test_rule_does_not_break_other_playbook_rules():
    # граница 30 суток, округление нормы, потолок 60, помета «приблизительно» остались на месте
    assert "30 суток" in PLAYBOOK or "30 дн" in PLAYBOOK
    assert "104,5 показывается как 104" in PLAYBOOK
    assert "60 видео" in PLAYBOOK
    assert PLAYBOOK.count("посчитано вручную, приблизительно") >= 1
    assert "сравнивать нужно точные значения" in PLAYBOOK.lower()


def test_four_digit_exact_value_is_not_equal_to_threshold_for_comments():
    exact = Fraction(99996, 100_000_000)  # 0,00099996
    assert shown(exact, 4) == Decimal("0.001")  # предусловие: на 4 знаках значение выглядит как порог
    # поэтому правило обязано требовать больше знаков для малых долей
    assert re.search(r"значащ|достаточно знаков|до первой отличающейся", rule_line())


def test_four_digit_exact_value_for_multiplier_near_three():
    exact = Fraction(299996, 100000)
    assert shown(exact, 4) == Decimal("3.0000")  # предусловие: на 4 знаках выглядит как порог
    assert re.search(r"значащ|достаточно знаков|до первой отличающейся", rule_line())


def test_rule_states_generic_trigger_for_custom_thresholds():
    assert re.search(r"settings\.yaml|свой порог|любого порога|порог из настроек", rule_line())


def test_rule_states_precision_of_likes_and_comments_ratios():
    assert re.search(r"лайк\w* ÷ просмотр\w*[^.]*знак|доли[^.]*знак", rule_line())
