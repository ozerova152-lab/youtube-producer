"""T37 (независимая проверка): схема «Путь от темы до плана» — контраст, ширины, масштаб, тёмная тема, наложения."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PAGE_URL = (ROOT / "site" / "index.html").as_uri()
SHOTS = ROOT / "test-results" / "t37"  # в .gitignore, бинарники не коммитятся
LI = "#scheme ol.scheme > li"

LUMINANCE_JS = """
(rgb) => {
  const c = rgb.match(/[\\d.]+/g).map(Number).slice(0, 3).map(v => {
    v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
"""


@pytest.fixture(scope="module")
def browser():
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def open_page(browser, width, **args):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, **args)
    page = ctx.new_page()
    page.goto(PAGE_URL)
    return page


def no_side_scroll(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def contrast(page, selector):
    return page.evaluate(
        """([sel, lumSrc]) => {
          const lum = eval(lumSrc);
          const el = document.querySelector(sel);
          const fg = getComputedStyle(el).color;
          let bgEl = el, bg;
          while (bgEl) { bg = getComputedStyle(bgEl).backgroundColor; if (!/rgba\\(.*, 0\\)|transparent/.test(bg)) break; bgEl = bgEl.parentElement; }
          const a = lum(fg), b = lum(bg);
          return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        }""",
        [selector, f"({LUMINANCE_JS})"],
    )


@pytest.mark.parametrize("width", [360, 768, 820, 1000])
def test_no_horizontal_scroll_and_no_overlaps(browser, width):
    page = open_page(browser, width)
    assert no_side_scroll(page)
    page.locator("#scheme").screenshot(path=str(SHOTS / f"scheme-{width}.png"))
    boxes = [page.locator(LI).nth(i).bounding_box() for i in range(6)]
    arrows = [page.locator(f"{LI} > svg.arrow").nth(i).bounding_box() for i in range(6)]

    def hit(a, b):
        return a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]

    # карточки не наползают друг на друга
    for i in range(6):
        for j in range(i + 1, 6):
            assert not hit(boxes[i], boxes[j]), (width, i, j)
    # стрелка (видимая) не пересекается с текстом/блоками чужих карточек и не вылезает за экран
    for i in range(5):
        if page.locator(f"{LI} > svg.arrow").nth(i).is_visible():
            for j in range(6):
                if j != i:
                    assert not hit(arrows[i], boxes[j]), (width, "arrow", i, "card", j)
            assert arrows[i]["x"] >= 0 and arrows[i]["x"] + arrows[i]["width"] <= width


@pytest.mark.parametrize("width", [768, 820])
def test_intermediate_widths_grid_three_by_two(browser, width):
    page = open_page(browser, width)
    ys = [round(page.locator(LI).nth(i).bounding_box()["y"]) for i in range(6)]
    assert len(set(ys[:3])) == 1 and len(set(ys[3:])) == 1 and ys[3] > ys[0]


def test_text_not_clipped_in_cards(browser):
    for width in (360, 768, 1000):
        page = open_page(browser, width)
        clipped = page.evaluate(
            """(sel) => [...document.querySelectorAll(sel)].filter(li =>
                [...li.querySelectorAll('h3,p,strong')].some(e => e.scrollWidth > e.clientWidth + 1 ||
                  e.getBoundingClientRect().right > li.getBoundingClientRect().right + 1)).length""",
            LI,
        )
        assert clipped == 0, width


def test_decision_contrast_at_least_4_5(browser):
    page = open_page(browser, 1000)
    for sel in (f"{LI}.decision h3", f"{LI}.decision p", f"{LI}.decision .who", f"{LI}.decision .number"):
        assert contrast(page, sel) >= 4.5, sel
    for sel in (f"{LI}:not(.decision) h3", f"{LI}:not(.decision) p"):
        assert contrast(page, sel) >= 4.5, sel
    # рамка выделения отличается от фона страницы не менее чем 3:1
    border = page.evaluate(f"getComputedStyle(document.querySelector('{LI}.decision')).borderTopColor")
    page_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    lum = lambda c: page.evaluate(f"({LUMINANCE_JS})", c)
    a, b = lum(border), lum(page_bg)
    assert (max(a, b) + 0.05) / (min(a, b) + 0.05) >= 3


def test_words_not_only_color_and_exactly_two_words_on_page_block(browser):
    page = open_page(browser, 1000)
    text = page.locator("#scheme").inner_text()
    assert text.count("Утверждаете вы") == 1 and text.count("Решаете вы") == 1
    assert page.locator(f"{LI}.decision").count() == 2


def test_large_font_and_zoom_do_not_break_cards(browser):
    # увеличенный шрифт: 32px корень на 360; «200% масштаб» = 180 css-px ширины
    for width, root in ((360, "32px"), (180, None)):
        page = open_page(browser, width)
        if root:
            page.add_style_tag(content=f"html{{font-size:{root} !important}}")
        assert no_side_scroll(page), (width, root)
        page.locator("#scheme").screenshot(path=str(SHOTS / f"scheme-zoom-{width}-{root}.png"))
        for i in range(6):
            b = page.locator(LI).nth(i).bounding_box()
            assert b["x"] >= 0 and b["x"] + b["width"] <= width + 1


def test_long_words_and_open_details_do_not_scroll_sideways(browser):
    page = open_page(browser, 360)
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert no_side_scroll(page)
    page.evaluate(
        "document.querySelectorAll('#scheme h3, #scheme p').forEach(e => e.textContent += ' Сверхдлинноеслово' + 'а'.repeat(8))"
    )
    assert no_side_scroll(page), "длинное слово (25 букв) в карточке вызывает горизонтальную прокрутку"


def test_dark_browser_theme_page_stays_readable(browser):
    page = open_page(browser, 1000, color_scheme="dark")
    page.screenshot(path=str(SHOTS / "full-dark-scheme.png"), full_page=True)
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "light"
    for sel in (f"{LI}:not(.decision) h3", f"{LI}.decision h3", "main h1"):
        assert contrast(page, sel) >= 4.5, sel


def test_link_is_clickable_and_not_covered_on_phone(browser):
    page = open_page(browser, 360, has_touch=True, is_mobile=True)
    link = page.get_by_role("link", name="Посмотреть полный пример")
    link.scroll_into_view_if_needed()
    box = link.bounding_box()
    top = page.evaluate(
        "([x,y]) => { const e = document.elementFromPoint(x,y); return !!e && (e.tagName === 'A' || !!e.closest('a')) && e.closest('a').textContent.includes('Посмотреть полный пример'); }",
        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
    )
    assert top, "ссылка перекрыта другим элементом"
    assert link.get_attribute("href").endswith("/tree/main/examples/demo/expected")
    # ссылка под схемой, не над ней
    assert box["y"] > page.locator(LI).nth(5).bounding_box()["y"]


def test_no_scripts_besides_copy_buttons_and_no_cdn():
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert len(re.findall(r"<script", html)) == 1
    assert not re.search(r'(src|href)="https?://[^"]*(cdn|googleapis|unpkg|jsdelivr)', html)
    scheme = html[html.index('<section id="scheme">'):html.index("</section>", html.index('<section id="scheme">'))]
    assert not re.search(r"on\w+=|style=|#[0-9a-fA-F]{3,8}\b", scheme)


def test_top_of_page_intact(browser):
    page = open_page(browser, 1000)
    body = page.inner_text("body")
    for needle in ("Скопировать сообщение для агента", "Как это работает", "Если что-то не получилось", "Скачать на GitHub", "Скопировать адрес"):
        assert needle in body, needle
    top = page.locator("main").inner_text()[:2500]
    assert not re.search(r"не\s+провер|без ключа|демо", top, re.IGNORECASE)
    assert page.locator("#example").count() == 0
