"""Независимая проверка T33 «Установка по ссылке»: от критериев приёмки, не от кода.

Проверяет: дословное совпадение сообщения агенту в README/README.en/витрине, копирование,
работу без JS и без стилей, запрет трудных слов выше «Быстрого старта», раздел AGENTS.md,
плашку WSL, docs/compatibility.md, ссылки и якоря.
"""

import html as htmllib
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
README_EN = (ROOT / "README.en.md").read_text(encoding="utf-8")
SITE_HTML = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
PAGE_URL = (ROOT / "site" / "index.html").as_uri()
REPO = "https://github.com/ozerova152-lab/youtube-producer"

CLIPBOARD_OK = """
window.__copied = null;
Object.defineProperty(navigator, 'clipboard', {value: {
  writeText: (t) => { window.__copied = t; return Promise.resolve(); }}});
"""
CLIPBOARD_DENIED = """
Object.defineProperty(navigator, 'clipboard', {value: {
  writeText: () => Promise.reject(new Error('denied'))}});
"""


def _message(text: str, heading: str) -> str:
    m = re.search(re.escape(heading) + r".*?```text\n(.*?)\n```", text, re.DOTALL)
    assert m, heading
    return m.group(1)


MSG_RU = _message(README, "## Установка одной фразой")
MSG_EN = _message(README_EN, "## Install with one phrase")
MSG_SITE = htmllib.unescape(
    re.search(r'<pre id="agent-message">(.*?)</pre>', SITE_HTML, re.DOTALL).group(1)
)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _page(browser, width=1000, **kw):
    return browser.new_context(viewport={"width": width, "height": 800}, **kw).new_page()


def _section(text: str, start: str, end: str) -> str:
    a = text.index(start)
    return text[a : text.index(end, a)]


# ---------- (1) сообщение ----------


def test_message_verbatim_identical_everywhere():
    assert MSG_RU == MSG_EN == MSG_SITE
    assert repr(MSG_RU).count("\\n") == 5  # ровно 6 строк
    assert "«" in MSG_RU and "»" in MSG_RU and "  " not in MSG_RU
    assert MSG_RU == MSG_RU.strip() and "\r" not in MSG_RU
    assert REPO in MSG_RU


def test_message_points_to_real_agents_section():
    m = re.search(r"раздел «([^»]+)»", MSG_RU)
    assert m and m.group(1) == "Установка по ссылке"
    assert re.search(r"^## Установка по ссылке$", AGENTS, re.MULTILINE)
    assert "AGENTS.md" in MSG_RU


def test_button_copies_exact_message_and_shows_state(browser):
    page = _page(browser)
    page.add_init_script(CLIPBOARD_OK)
    page.goto(PAGE_URL)
    btn = page.get_by_role("button", name="Скопировать сообщение для агента")
    assert btn.is_visible()
    btn.click()
    assert page.evaluate("window.__copied") == MSG_RU
    assert page.get_by_role("button", name="Сообщение скопировано").is_visible()


def test_button_clipboard_error_message_and_text_kept(browser):
    page = _page(browser)
    page.add_init_script(CLIPBOARD_DENIED)
    page.goto(PAGE_URL)
    page.get_by_role("button", name="Скопировать сообщение для агента").click()
    assert page.get_by_text("Не получилось скопировать. Выделите сообщение вручную").is_visible()
    assert page.locator("#agent-message").inner_text() == MSG_RU
    # повтор после ошибки не ломает страницу
    page.get_by_role("button", name="Скопировать сообщение для агента").click()
    assert page.get_by_text("Не получилось скопировать. Выделите сообщение вручную").is_visible()


def test_no_javascript_text_visible_selectable_button_hidden(browser):
    page = _page(browser, java_script_enabled=False)
    page.goto(PAGE_URL)
    assert page.locator("#agent-message").inner_text() == MSG_RU
    assert not page.locator("#copy-message").is_visible()
    assert page.locator("#agent-message").evaluate("e => getComputedStyle(e).userSelect") != "none"
    assert page.locator("#repo-address").is_visible()


def test_message_selectable_with_js(browser):
    page = _page(browser)
    page.goto(PAGE_URL)
    page.locator("#agent-message").click(click_count=3)  # тройной клик выделяет строку
    assert "Перед каждой командой" in page.evaluate("window.getSelection().toString()")
    page.locator("#agent-message").click()
    page.keyboard.press("Control+A")  # выделение всей страницы не блокируется скриптом
    assert MSG_RU in page.evaluate("window.getSelection().toString()").replace("\n\n", "\n")


def test_without_styles_message_and_text_readable(browser):
    ctx = browser.new_context(viewport={"width": 1000, "height": 800})
    ctx.route("**/*.css", lambda r: r.abort())
    page = ctx.new_page()
    page.goto(PAGE_URL)
    assert page.locator("#agent-message").inner_text() == MSG_RU
    body = page.locator("body").inner_text()
    assert "Установка одной фразой" in body and "отвечайте «да»" in body


@pytest.mark.parametrize("js", [True, False])
def test_phone_360_no_horizontal_scroll_closed_and_open(browser, js):
    page = _page(browser, width=360, java_script_enabled=js)
    page.goto(PAGE_URL)
    fits = "document.documentElement.scrollWidth <= window.innerWidth"
    assert page.evaluate(fits) if js else True
    n = page.locator("#troubleshooting details").count()
    assert n == 5
    for i in range(n):
        d = page.locator("#troubleshooting details").nth(i)
        assert d.evaluate("e => e.open") is False
        d.locator("summary").click()
        assert d.evaluate("e => e.open") is True
        box = d.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 361
    if js:
        assert page.evaluate(fits)
    box = page.locator("#agent-message").bounding_box()
    assert box["x"] + box["width"] <= 360


# ---------- (2) слова ----------

BANNED = re.compile(
    r"WSL|\bmake\b|\bgit\b|Python|терминал|демо|\bтест|без ключа|Нет ключа YouTube", re.IGNORECASE
)


def _strip_details_and_message(md: str) -> str:
    md = re.sub(r"<details>.*?</details>", "", md, flags=re.DOTALL)
    return re.sub(r"```text\n.*?\n```", "", md, flags=re.DOTALL)


def test_readme_top_has_no_hard_words():
    top = README[: README.index("## Быстрый старт")]
    clean = _strip_details_and_message(top)
    hits = BANNED.findall(clean)
    assert not hits, hits


def test_readme_en_top_has_no_hard_words():
    top = README_EN[: README_EN.index("## Quick start")]
    clean = _strip_details_and_message(top)
    hits = re.findall(
        r"WSL|\bmake\b|\bgit\b|Python|terminal|demo|without a key|no key", clean, re.IGNORECASE
    )
    assert not hits, hits


def test_site_visible_text_has_no_hard_words(browser):
    page = _page(browser)
    page.goto(PAGE_URL)
    text = page.evaluate(
        "() => { const c = document.body.cloneNode(true);"
        " c.querySelectorAll('details, script, style').forEach(e => e.remove());"
        " c.querySelector('#agent-message').remove(); return c.innerText; }"
    )
    hits = BANNED.findall(text)
    assert not hits, hits
    # описание страницы тоже
    assert not BANNED.search(re.search(r'name="description" content="([^"]*)"', SITE_HTML).group(1))


def test_three_check_commands_only_in_quick_start_between_step3_and_step4():
    marker = "produce --channel data/demo"
    for name, text in (("README", README), ("README.en", README_EN)):
        positions = [m.start() for m in re.finditer(re.escape(marker), text)]
        assert len(positions) >= 3, name
        # все вхождения в одном блоке между Шагом 3 и Шагом 4
        s3 = text.index("### Шаг 3") if name == "README" else text.index("### Step 3")
        s4 = text.index("### Шаг 4") if name == "README" else text.index("### Step 4")
        assert all(s3 < p < s4 for p in positions), name
        assert text.count("```bash") >= 1
    assert marker not in SITE_HTML and "examples/demo" not in SITE_HTML.split('<section id="scheme">')[0]  # T37: ссылка на examples/demo/expected только под схемой
    assert "### Проверьте, что всё работает" in README


def test_old_caption_gone():
    old = "Пример на демо-данных" + ", не реальный канал"
    for p in (
        list((ROOT / "site").rglob("*"))
        + list((ROOT / "docs" / "spec").rglob("*"))
        + list((ROOT / "tests").glob("*.py"))
        + [ROOT / "DESIGN.md", ROOT / "README.md", ROOT / "README.en.md"]
    ):
        if p.is_file() and p.suffix in {".html", ".css", ".md", ".py", ".js"}:
            assert old not in p.read_text(encoding="utf-8"), p
    assert "Пример на выдуманном канале" not in SITE_HTML  # T37: подпись ушла вместе с примером


# ---------- (3) AGENTS.md ----------


def _agents_section() -> str:
    return _section(AGENTS, "## Установка по ссылке", "\n## Запреты")


def test_agents_section_has_all_points():
    s = _agents_section()
    for needle in (
        "Python",
        "3.12",
        "`git`",
        "`make`",
        "/mnt/c",
        "«да»",
        "sudo",
        "администратор",
        "пароль",
        "`make setup`",
        "молча",
        "Всё установилось и работает, расскажите про свой канал",
        "`make add-key`",
        "не запускаешь",
        "WSL",
        "PowerShell",
        "перезагрузк",
        "docs/windows-wsl.md",
        "**Mac.**",
        "**Linux.**",
        "playbooks/no-terminal.md",
        "~/youtube-producer",
    ):
        assert needle in s, needle
    assert "не ставь молча" in s or "ничего не ставь" in s
    assert "не говори" in s and "демо" in s and "дату демо" in s
    assert "не просишь" in s  # пароль/ключ
    assert (ROOT / "docs" / "windows-wsl.md").exists()
    # clone строго в домашнюю папку
    assert re.search(
        r"git clone https://github\.com/ozerova152-lab/youtube-producer\.git ~/youtube-producer", s
    )
    # make setup идёт перед пробой, проба последним шагом установки
    assert s.index("`make setup`") < s.index("проверочный прогон") < s.index("Всё установилось")
    # раздел «Проверьте, что всё работает» реально существует в README
    assert "### Проверьте, что всё работает" in README
    assert "Установка одной фразой" in README


def test_agents_does_not_contradict_prohibitions():
    s = _agents_section()
    # агент не запускает add-key и не просит ключ: и в «Запретах» то же самое
    assert "Не проси ключ в чате" in AGENTS and "не запускай `make add-key` сам" in AGENTS
    assert "make add-key" not in re.sub(r"[^\n]*не запускаешь[^\n]*", "", s) or "не запускаешь" in s
    # подтверждения --confirm в разделе нет
    assert "--confirm" not in s
    # правила Windows совпадают с общим правилом «Команды»
    assert "PowerShell не трогай" in AGENTS and "PowerShell не трогай" in s
    # режим без терминала в AGENTS и в разделе ссылаются на один файл
    assert AGENTS.count("playbooks/no-terminal.md") >= 2
    # раздел находится до «Запретов» и после «Режима без терминала»
    assert (
        AGENTS.index("## Режим без терминала")
        < AGENTS.index("## Установка по ссылке")
        < AGENTS.index("## Запреты")
    )


def test_playbook_month_branch_points_to_section():
    pb = (ROOT / "playbooks" / "00-month.md").read_text(encoding="utf-8")
    assert "Установка по ссылке" in pb


# ---------- (4) плашка WSL ----------


def test_wsl_plate_texts():
    ru = _section(README, "- **Я на Windows.**", "- **Не хватает")
    assert (
        "Claude Code или Codex" in ru and "обычном чате WSL не нужен" in ru and "Cowork" not in ru
    )
    en = _section(README_EN, "- **I am on Windows.**", "- **Python, make")
    assert "Claude Code or Codex" in en and "not needed" in en and "Cowork" not in en
    site = re.search(r'<details id="windows-wsl">.*?</details>', SITE_HTML, re.DOTALL).group(0)
    assert (
        "Claude Code или Codex" in site
        and "обычном чате WSL не нужен" in site
        and "Cowork" not in site
    )
    for doc in ("docs/windows-wsl.md", "docs/windows-wsl.en.md"):
        head = (ROOT / doc).read_text(encoding="utf-8")[:900]
        assert "Cowork" not in head, doc


def test_readme_details_closed_by_default():
    for t in (README, README_EN):
        assert "<details>" in t and "<details open" not in t
    assert "<details open" not in SITE_HTML and not re.search(r"<details[^>]*\sopen", SITE_HTML)


# ---------- (5) compatibility ----------


def test_compatibility_flags_link_path_as_not_run_and_status_once():
    c = (ROOT / "docs" / "dev" / "agent-status.md").read_text(encoding="utf-8")  # T34: заметка разработчика
    sec = c[c.index("## Установка по ссылке"):]
    assert "не прогоняли" in sec and "на реальной машине" in sec
    assert c.count("## Статус") == 1
    assert "Установка по ссылке" not in (ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8")
    # статус по агентам (строки с названиями) не продублирован в новом разделе
    assert "Claude Code" not in sec and "Codex" not in sec


def test_site_has_no_not_verified_forms(browser):
    page = _page(browser)
    page.goto(PAGE_URL)
    assert not re.search(
        r"не\s*провер", SITE_HTML + page.locator("body").inner_text(), re.IGNORECASE
    )


# ---------- (6) размер, паритет, ссылки ----------


def test_readme_size_and_parity():
    assert len(README.splitlines()) <= 165
    h = lambda t: [x for x in re.findall(r"^(#{1,3}) ", t, re.MULTILINE)]
    assert h(README) == h(README_EN)
    assert README.count("<details>") == README_EN.count("<details>") == README.count("</details>")
    ru_steps = re.findall(r"^### (?:Шаг|Step) \d", README, re.MULTILINE) + re.findall(
        r"^### (?:Шаг|Step) \d", README_EN, re.MULTILINE
    )
    assert len(ru_steps) == 10


def _anchor(h: str) -> str:
    h = h.strip().lower()
    h = re.sub(r"[^\w\- ]", "", h, flags=re.UNICODE)
    return h.replace(" ", "-")


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        "README.en.md",
        "docs/compatibility.md",
        "docs/windows-wsl.md",
        "docs/windows-wsl.en.md",
    ],
)
def test_relative_links_and_anchors_alive(name):
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http", "mailto")):
            continue
        file_part, _, anchor = target.partition("#")
        dest = (path.parent / file_part).resolve() if file_part else path
        assert dest.exists(), (name, target)
        if anchor and dest.suffix == ".md":
            heads = [
                _anchor(h)
                for h in re.findall(
                    r"^#{1,6} (.+)$", dest.read_text(encoding="utf-8"), re.MULTILINE
                )
            ]
            assert anchor.lower() in heads, (name, target, heads)


def test_site_links_to_repo_files_exist():
    for rel in re.findall(r"youtube-producer/blob/main/([^\"#]+)", SITE_HTML):
        assert (ROOT / rel).exists(), rel


def test_spec_matches_real_texts():
    flows = (ROOT / "docs" / "spec" / "04-user-flows.md").read_text(encoding="utf-8")
    for needle in (
        "Скопировать сообщение для агента",
        "Сообщение скопировано",
        "Не получилось скопировать. Выделите сообщение вручную",
        "Установка по ссылке",
        "Всё установилось и работает, расскажите про свой канал",
    ):
        assert needle in flows, needle
    for line in MSG_RU.splitlines():
        assert line in flows, line  # сообщение в потоке 1 дословно, построчно
    spec1 = (ROOT / "docs" / "spec" / "01-functional-requirements.md").read_text(encoding="utf-8")
    assert "Скопировать сообщение для агента" in spec1
