"""UI-тест потока 6 «Посетитель страницы-витрины» (docs/spec/04-user-flows.md).

Страница открывается как файл: сети нет, данные статические. Тексты сверяются
с потоком дословно; скриншоты каждого состояния кладутся в test-results/showcase/.
"""

import re
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PAGE_URL = (SITE / "index.html").as_uri()
SHOTS = ROOT / "test-results" / "showcase"
REPO = "https://github.com/ozerova152-lab/youtube-producer"
COPY_FAILED = "Не получилось скопировать. Выделите адрес вручную"

# Подмена буфера обмена: настоящий требует разрешений и недетерминирован.
CLIPBOARD_OK = """
window.__copied = null;
Object.defineProperty(navigator, 'clipboard', {value: {
  writeText: (t) => { window.__copied = t; return Promise.resolve(); }}});
"""
CLIPBOARD_DENIED = """
Object.defineProperty(navigator, 'clipboard', {value: {
  writeText: () => Promise.reject(new Error('denied'))}});
"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def open_page(browser: Browser, width=1000, height=800, **context_args) -> Page:
    page = browser.new_context(viewport={"width": width, "height": height}, **context_args)
    return page.new_page()


def shot(page: Page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def test_visitor_reads_blocks_and_reaches_github(browser):
    page = open_page(browser)
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(PAGE_URL)
    page.wait_for_load_state("networkidle")

    assert page.get_by_role("heading", level=1).inner_text() == "AI-продюсер YouTube-канала"
    assert page.get_by_text(
        "Находит залётные видео вашей ниши, разбирает причины и готовит стратегию, "
        "план и брифы. Решает и публикует всегда человек."
    ).first.is_visible()

    headings = [h.inner_text() for h in page.get_by_role("heading", level=2).all()]
    assert headings == ["Как это работает", "Как запустить", "Пример результата"]
    assert page.locator("#how-it-works .steps li").count() == 5
    assert page.get_by_text("Решает и публикует всегда человек.", exact=True).is_visible()
    assert page.get_by_role("heading", name="В Claude Code").is_visible()
    assert page.get_by_role("heading", name="В Codex").is_visible()
    assert page.get_by_text("Codex проверен лишь на базовом уровне.").is_visible()
    assert page.get_by_text("Нет ключа YouTube? Можно загрузить видео из файла.").is_visible()
    assert page.get_by_text("Пример на демо-данных, не реальный канал.").is_visible()
    assert page.get_by_text(
        "Откроется страница репозитория: нажмите Code → Download ZIP."
    ).is_visible()
    assert page.locator("#repo-address").inner_text() == REPO

    # Кнопка в начале и в конце: обе ведут на репозиторий, а не «в никуда».
    buttons = page.get_by_role("button", name="Скачать на GitHub").all()
    assert len(buttons) == 2
    assert all(b.get_attribute("href") == REPO for b in buttons)

    # Страница самодостаточна: ни одного обращения во внешнюю сеть.
    assert all(url.startswith("file://") for url in requests), requests
    shot(page, "desktop")


def test_page_weight_under_one_megabyte(browser):
    page = open_page(browser)
    files = []
    page.on("request", lambda r: files.append(Path(r.url.removeprefix("file://"))))
    page.goto(PAGE_URL)
    page.wait_for_load_state("networkidle")
    assert sum(f.stat().st_size for f in files) < 1_000_000


def test_phone_360_has_no_horizontal_scroll_and_shows_hint(browser):
    page = open_page(browser, width=360, height=640)
    page.goto(PAGE_URL)
    page.wait_for_load_state("networkidle")

    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    hint = page.get_by_text(
        "Запускать проект нужно на компьютере. Скопируйте адрес репозитория, "
        "чтобы открыть его там."
    )
    assert hint.is_visible()
    # Подсказка открывает блок «Как запустить»: идёт сразу после его заголовка.
    first = page.locator("#how-to-run > :nth-child(2)")
    assert first.inner_text().startswith("Запускать проект нужно на компьютере")
    button = page.get_by_role("button", name="Скачать на GitHub").first
    box = button.bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= 360
    shot(page, "phone-360")


def test_desktop_hides_phone_hint(browser):
    page = open_page(browser)
    page.goto(PAGE_URL)
    assert not page.locator(".phone-only").is_visible()


def test_without_javascript_address_stays_as_text(browser):
    page = open_page(browser, java_script_enabled=False)
    page.goto(PAGE_URL)
    assert not page.locator("#copy-address").is_visible()
    assert page.locator("#repo-address").inner_text() == REPO
    assert page.get_by_role("button", name="Скачать на GitHub").first.is_visible()
    shot(page, "no-javascript")


def test_copy_address_shows_confirmation(browser):
    page = open_page(browser)
    page.add_init_script(CLIPBOARD_OK)
    page.goto(PAGE_URL)
    page.get_by_role("button", name="Скопировать адрес").click()
    assert page.get_by_role("button", name="Адрес скопирован").is_visible()
    assert page.evaluate("window.__copied") == REPO
    shot(page, "copied")


def test_copy_denied_shows_manual_hint_and_keeps_address(browser):
    page = open_page(browser)
    page.add_init_script(CLIPBOARD_DENIED)
    page.goto(PAGE_URL)
    page.get_by_role("button", name="Скопировать адрес").click()
    assert page.get_by_text(COPY_FAILED).is_visible()
    assert page.locator("#repo-address").inner_text() == REPO
    shot(page, "copy-denied")


def test_slow_network_text_and_button_readable_without_styles(browser):
    page = open_page(browser)
    page.route(re.compile(r"\.(css|woff2)$"), lambda route: route.abort())
    page.goto(PAGE_URL)
    assert page.get_by_role("heading", level=1).is_visible()
    assert page.get_by_role("button", name="Скачать на GitHub").first.is_visible()
    assert page.locator("#repo-address").is_visible()
    shot(page, "without-styles")


def test_long_address_wraps_on_phone(browser):
    page = open_page(browser, width=360, height=640)
    page.goto(PAGE_URL)
    page.evaluate(
        "document.getElementById('repo-address').textContent ="
        " 'https://github.com/' + 'a'.repeat(80) + '/youtube-producer'"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_markup_has_no_hardcoded_colors_or_inline_styles():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", html)
    assert "style=" not in html
