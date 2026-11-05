"""T37: на витрине вместо примера результата схема «Путь от темы до плана» из шести квадратиков."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PAGE_URL = (SITE / "index.html").as_uri()
HTML = (SITE / "index.html").read_text(encoding="utf-8")
CSS = (SITE / "theme.css").read_text(encoding="utf-8")
LINK = "https://github.com/ozerova152-lab/youtube-producer/tree/main/examples/demo/expected"
NAMES = ["Ваш канал и тема", "Залёты", "Разбор причин", "Стратегия", "Брифы", "План на месяц"]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def page_at(browser, width, **args):
    return browser.new_context(viewport={"width": width, "height": 800}, **args).new_page()


def test_six_steps_in_working_order_with_short_captions(browser):
    page = page_at(browser, 1000)
    page.goto(PAGE_URL)
    items = page.locator("#scheme ol.scheme > li")
    assert items.count() == 6
    for i, name in enumerate(NAMES):
        text = items.nth(i).inner_text()
        assert f"{i + 1}." in text and name in text, (i, text)
        assert len(items.nth(i).locator("p").inner_text()) <= 80  # одна короткая подпись
    assert [h.inner_text() for h in page.get_by_role("heading", level=2).all()][-1] == "Путь от темы до плана"


def test_only_human_decision_steps_are_marked_and_colored(browser):
    page = page_at(browser, 1000)
    page.goto(PAGE_URL)
    items = page.locator("#scheme ol.scheme > li")
    marked = [i for i in range(6) if "decision" in (items.nth(i).get_attribute("class") or "")]
    assert marked == [3, 4]
    assert "Утверждаете вы" in items.nth(3).inner_text() and "Решаете вы" in items.nth(4).inner_text()
    for i in (0, 1, 2, 5):
        assert not re.search(r"Утверждаете вы|Решаете вы", items.nth(i).inner_text())
    colors = {items.nth(i).evaluate("e => getComputedStyle(e).backgroundColor") for i in marked}
    plain = {items.nth(i).evaluate("e => getComputedStyle(e).backgroundColor") for i in (0, 1, 2, 5)}
    assert len(colors) == 1 and colors.isdisjoint(plain)  # один цвет для обоих шагов, отличный от остальных


def test_phone_squares_are_stacked_without_horizontal_scroll(browser):
    page = page_at(browser, 360)
    page.goto(PAGE_URL)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    boxes = [page.locator("#scheme ol.scheme > li").nth(i).bounding_box() for i in range(6)]
    assert all(b and b["x"] >= 0 and b["x"] + b["width"] <= 360 for b in boxes)
    assert all(boxes[i + 1]["y"] > boxes[i]["y"] + boxes[i]["height"] for i in range(5))  # друг под другом
    assert len({round(b["x"]) for b in boxes}) == 1


def test_desktop_grid_is_three_by_two(browser):
    page = page_at(browser, 1000)
    page.goto(PAGE_URL)
    ys = [round(page.locator("#scheme ol.scheme > li").nth(i).bounding_box()["y"]) for i in range(6)]
    assert len(set(ys[:3])) == 1 and len(set(ys[3:])) == 1 and ys[3] > ys[0]


def test_readable_without_javascript_and_without_styles(browser):
    page = page_at(browser, 360, java_script_enabled=False)
    page.goto(PAGE_URL)
    assert page.locator("#scheme li").first.is_visible()
    page = page_at(browser, 360)
    page.route(re.compile(r"\.(css|woff2)$"), lambda route: route.abort())
    page.goto(PAGE_URL)
    text = page.locator("#scheme ol.scheme").inner_text()
    positions = [text.index(name) for name in NAMES]
    assert positions == sorted(positions) and "Утверждаете вы" in text and "Решаете вы" in text


def test_full_example_link_points_to_demo_expected_which_exists():
    assert f'<a href="{LINK}">Посмотреть полный пример</a>' in HTML
    assert (ROOT / "examples" / "demo" / "expected").is_dir()


def test_old_example_block_is_gone():
    for gone in ("Пример результата", "Пример на выдуманном канале", "×12.68", "<table", "Бриф 1:"):
        assert gone not in HTML, gone
    assert 'id="example"' not in HTML and "Пример взят из examples/demo" not in HTML


def test_markup_rules_icons_colors_and_weight():
    section = HTML[HTML.index('<section id="scheme">'):HTML.index('<section id="download"')]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", section) and "style=" not in section
    assert section.count("<svg") == 12 and "aria-hidden=\"true\"" in section  # шесть иконок и шесть стрелок
    assert "<img" not in section and "<script" not in section
    assert "--decision-background" in CSS and "--decision-border" in CSS
    assert sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file()) < 1_000_000


def test_no_verification_words_in_scheme_and_spec_mentions_it():
    text = re.sub(r"<[^>]+>", "", HTML[HTML.index('<section id="scheme">'):HTML.index('<section id="download"')])
    assert not re.search(r"проверен|не\s+провер|tested", text, re.IGNORECASE)
    flows = (ROOT / "docs/spec/04-user-flows.md").read_text(encoding="utf-8")
    layer1 = (ROOT / "docs/spec/01-functional-requirements.md").read_text(encoding="utf-8")
    for doc in (flows, layer1):
        assert "Путь от темы до плана" in doc and "Посмотреть полный пример" in doc and "examples/demo/expected" in doc
        assert "Пример на выдуманном канале" not in doc
