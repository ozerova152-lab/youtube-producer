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
MESSAGE_FAILED = "Не получилось скопировать. Выделите сообщение вручную"
README_TEXT = (ROOT / "README.md").read_text(encoding="utf-8")
# готовое сообщение агенту: один и тот же текст в README, README.en.md и на витрине (T33)
AGENT_MESSAGE = re.search(r"## Установка одной фразой.*?```text\n(.*?)\n```", README_TEXT, re.DOTALL).group(1)

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
    assert headings == ["Установка одной фразой", "Как это работает", "Если что-то не получилось",
                        "Пример результата"]
    assert page.locator("#how-it-works .steps li").count() == 5
    assert page.get_by_text("Решает и публикует всегда человек.", exact=True).is_visible()
    # готовое сообщение агенту видно сразу и совпадает с README
    assert page.locator("#agent-message").inner_text() == AGENT_MESSAGE
    assert REPO in AGENT_MESSAGE and "Установка по ссылке" in AGENT_MESSAGE
    assert page.get_by_role("button", name="Скопировать сообщение для агента").is_visible()
    assert page.get_by_text("отвечайте «да» на его вопросы", exact=False).first.is_visible()
    # трудные слова не стоят в основной части: только в раскрывающихся блоках
    visible = page.evaluate(
        "() => { const c = document.querySelector('main').cloneNode(true);"
        " c.querySelectorAll('details, pre').forEach(e => e.remove()); return c.innerText; }")
    for word in ("WSL", "make", "Python", "git "):
        assert word not in visible, word
    # блоки «Если что-то не получилось» закрыты и раскрываются
    blocks = page.locator("#troubleshooting details")
    assert blocks.count() == 5
    assert all(not blocks.nth(i).evaluate("e => e.open") for i in range(5))
    wsl = page.locator("#windows-wsl")
    assert not page.get_by_text("Если застряли", exact=False).first.is_visible()
    wsl.locator("summary").click()
    text = wsl.inner_text()
    assert ("Если вы запускаете Claude Code или Codex на Windows, один раз нужно поставить WSL: это Linux "
            "внутри Windows") in text
    assert "Для работы в обычном чате WSL не нужен." in text and "Cowork" not in text
    assert "один разовый шаг, около 20–30 минут" in text
    assert ("Я на Windows и ничего не понимаю в терминале. Помоги поставить WSL и дойти до запуска проекта, "
            "объясняй каждый шаг") in text
    assert "Если застряли" in text and "Пароль при вводе не показывается" in text
    assert "включить в BIOS" in text and "имя@компьютер" in text
    manual = page.locator("#manual-install")
    manual.locator("summary").click()
    steps = manual.locator("ol > li")
    assert steps.count() == 3
    assert "Скачайте проект" in steps.nth(0).inner_text() and "make setup" in steps.nth(0).inner_text()
    assert "Откройте папку проекта в вашем агенте" in steps.nth(1).inner_text()
    assert "Прочитай AGENTS.md и запусти месяц" in steps.nth(2).inner_text()
    assert "Клонируйте" not in manual.inner_text()
    # три подсказки одинаковой структуры и примерно одной длины, без главного агента
    cards = manual.locator(".grid article")
    assert cards.count() == 3
    lengths = [len(cards.nth(i).inner_text()) for i in range(3)]
    assert max(lengths) - min(lengths) < 40, lengths
    assert page.get_by_role("heading", name="В Claude Code").is_visible()
    assert page.get_by_role("heading", name="В Claude Cowork").is_visible()
    assert page.get_by_role("heading", name="В Codex").is_visible()
    status = page.locator("#status")
    assert status.is_visible()
    assert status.inner_text() == (
        "Полностью проверен в Claude Code и Codex. Рассчитан и на другие агенты: те же инструкции "
        "работают без скрипта сбора данных, данные можно вставить в чат. Расскажите, как получилось")
    assert status.get_by_role("link", name="Расскажите, как получилось").get_attribute("href") == (
        "https://github.com/ozerova152-lab/youtube-producer/issues")
    # у Codex понятный путь: дать ссылку на репозиторий и написать фразу
    codex_card = manual.locator(".grid article").nth(2)
    assert "Дайте Codex ссылку на репозиторий" in codex_card.inner_text()
    assert "Изучи youtube-producer и помоги начать" in codex_card.inner_text()
    assert codex_card.get_by_role("link", name="репозиторий").get_attribute("href") == (
        "https://github.com/ozerova152-lab/youtube-producer")
    # подробный статус остаётся в README; на витрине нет ни одной формы «не провер…»
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"не\s+провер", page.locator("body").inner_text(), re.IGNORECASE)
    assert not re.search(r"не\s+провер", html, re.IGNORECASE)
    assert "Основной путь" not in html and "Cowork мы" not in html
    assert page.get_by_text("лишь на базовом уровне", exact=False).count() == 0
    assert page.get_by_text("Нет ключа YouTube?").count() == 0  # T33: про «без ключа» на витрине не пишем
    assert page.get_by_text("Пример на выдуманном канале, не реальный.").is_visible()
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
    # Подсказка открывает блок установки: идёт сразу после его заголовка.
    first = page.locator("#install-by-link > :nth-child(2)")
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


SITE_TEXT_SUFFIXES = {".html", ".css", ".js", ".md", ".txt", ".svg", ".json"}
# Ключ Google API: «AIza» и 35 символов; присвоение YOUTUBE_API_KEY с непустым значением.
KEY_PATTERNS = (r"AIza[0-9A-Za-z_\-]{35}", r"YOUTUBE_API_KEY\s*[=:]\s*[\"']?[^\s\"'<]+")


def test_site_files_have_no_api_keys():
    """Слой 1 и поток 6: на странице-витрине нет ключей (страница открыта всему интернету)."""
    files = [p for p in SITE.rglob("*") if p.is_file() and p.suffix in SITE_TEXT_SUFFIXES]
    assert (SITE / "index.html") in files
    found = [
        f"{path.relative_to(ROOT)}: {pattern}"
        for path in files
        for pattern in KEY_PATTERNS
        if re.search(pattern, path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not found, found


def test_example_block_comes_from_demo_data(browser):
    """T15: пример результата взят из examples/demo, а не условный."""
    page = open_page(browser)
    page.goto(PAGE_URL)
    row = page.locator("#example table tbody tr").first.inner_text()
    for cell in ("Как использовать нейросеть: выпуск 1", "52 000", "4 100", "×12.68"):
        assert cell in row
    brief = (ROOT / "examples/demo/expected/briefs/01.md").read_text(encoding="utf-8")
    assert "Бриф 1: Нейросеть для таблиц без формул" in brief
    assert page.get_by_role("heading", name="Бриф 1: Нейросеть для таблиц без формул").is_visible()
    first_15 = re.search(r"Первые 15 секунд: (.+)", brief).group(1)
    assert first_15 in page.locator("#example article").inner_text().replace("\n", " ")
    assert page.get_by_text("Пример на выдуманном канале, не реальный.").is_visible()
    # Старого условного примера нет.
    assert "монтажёра" not in page.content()


def test_github_fallback_phrase_next_to_address(browser):
    page = open_page(browser)
    page.goto(PAGE_URL)
    assert page.get_by_text("Если GitHub не открывается, попробуйте позже.").is_visible()
    assert page.locator("#repo-address").inner_text() == REPO


def test_demo_table_row_matches_report_numbers():
    """Числа в таблице совпадают с демо-запуском (examples/demo/import.csv)."""
    import csv

    rows = list(csv.DictReader((ROOT / "examples/demo/import.csv").open(encoding="utf-8")))
    first = next(r for r in rows if r["id"] == "demo_v01")
    assert f"{int(first['views']):,}".replace(",", " ") == "52 000"
    assert first["title"] in (SITE / "index.html").read_text(encoding="utf-8")


def test_copy_message_shows_confirmation_and_copies_full_text(browser):
    page = open_page(browser)
    page.add_init_script(CLIPBOARD_OK)
    page.goto(PAGE_URL)
    page.get_by_role("button", name="Скопировать сообщение для агента").click()
    assert page.get_by_role("button", name="Сообщение скопировано").is_visible()
    assert page.evaluate("window.__copied") == AGENT_MESSAGE
    shot(page, "message-copied")


def test_copy_message_denied_shows_manual_hint_and_keeps_text(browser):
    page = open_page(browser)
    page.add_init_script(CLIPBOARD_DENIED)
    page.goto(PAGE_URL)
    page.get_by_role("button", name="Скопировать сообщение для агента").click()
    assert page.get_by_text(MESSAGE_FAILED).is_visible()
    assert page.locator("#agent-message").inner_text() == AGENT_MESSAGE


def test_without_javascript_message_stays_as_selectable_text(browser):
    page = open_page(browser, java_script_enabled=False)
    page.goto(PAGE_URL)
    assert not page.locator("#copy-message").is_visible()
    assert page.locator("#agent-message").inner_text() == AGENT_MESSAGE
    shot(page, "no-javascript-message")


def test_phone_360_message_wraps_without_horizontal_scroll(browser):
    page = open_page(browser, width=360, height=640)
    page.goto(PAGE_URL)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    box = page.locator("#agent-message").bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= 360
    page.locator("#windows-wsl summary").click()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_same_message_in_readmes_and_site():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    site = re.search(r'<pre id="agent-message">(.*?)</pre>', html, re.DOTALL).group(1)
    en = re.search(r"## Install with one phrase.*?```text\n(.*?)\n```",
                   (ROOT / "README.en.md").read_text(encoding="utf-8"), re.DOTALL).group(1)
    assert site == AGENT_MESSAGE == en
