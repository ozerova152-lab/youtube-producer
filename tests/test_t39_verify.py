"""T39 (независимая проверка): под схемой нет ссылки на пример, нижний призыв на месте, без дыр и скачка вёрстки."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PAGE_URL = (ROOT / "site" / "index.html").as_uri()
HTML = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
SHOTS = ROOT / "test-results" / "t39"  # в .gitignore, бинарники не коммитятся
NAMES = ["Ваш канал и тема", "Залёты", "Разбор причин", "Стратегия", "Брифы", "План на месяц"]


@pytest.fixture(scope="module")
def browser():
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def test_no_example_mentions_anywhere_in_page_source_or_readmes():
    for text in (HTML, (ROOT / "README.md").read_text(encoding="utf-8"), (ROOT / "README.en.md").read_text(encoding="utf-8")):
        low = text.lower()
        assert "полный пример" not in low and "see the full example" not in low
    assert "examples/" not in HTML and "examples/demo" not in HTML.lower()


def test_scheme_block_structure_and_marks():
    section = HTML.split('<section id="scheme">')[1].split("</section>")[0]
    assert "<a " not in section and "href" not in section
    items = re.findall(r"<li[ >].*?</li>", section, re.DOTALL)
    assert len(items) == 6
    for item, name in zip(items, NAMES):
        assert name in re.sub(r"<[^>]+>", " ", item), name
    assert "Утверждаете вы" in items[3] and "Решаете вы" in items[4]
    assert section.count("Утверждаете вы") == 1 and section.count("Решаете вы") == 1


@pytest.mark.parametrize("width", [360, 1000])
def test_layout_without_js_download_block_in_place(browser, width):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, java_script_enabled=False)
    page = ctx.new_page()
    page.goto(PAGE_URL)
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert page.locator("#scheme a").count() == 0
    assert page.locator("#scheme ol.scheme > li").count() == 6
    assert "Цветом выделены шаги, где решаете вы" in page.locator("#scheme").inner_text()
    btn = page.locator("#download a", has_text="Скачать на GitHub")
    assert btn.is_visible()
    assert page.locator("#repo-address").inner_text() == "https://github.com/ozerova152-lab/youtube-producer"
    # без JS кнопка «Скопировать адрес» скрыта (hidden), адрес текстом
    assert not page.locator("#copy-address").is_visible()
    # зазор между концом схемы и нижним блоком — не дыра и не нахлёст
    caption_bottom = page.locator("#scheme p.caption").last.bounding_box()
    dl = page.locator("#download").bounding_box()
    gap = dl["y"] - (caption_bottom["y"] + caption_bottom["height"])
    assert 0 <= gap <= 120, gap
    # в нижнем блоке порядок сверху вниз: кнопка, подпись, адрес
    ys = [btn.bounding_box()["y"], page.locator("#repo-address").bounding_box()["y"]]
    assert ys == sorted(ys)
    page.screenshot(path=str(SHOTS / f"page-{width}.png"), full_page=True)
    ctx.close()


def test_copy_button_present_with_js(browser):
    page = browser.new_context(viewport={"width": 360, "height": 900}).new_page()
    page.goto(PAGE_URL)
    assert page.get_by_role("button", name="Скопировать адрес").is_visible()
