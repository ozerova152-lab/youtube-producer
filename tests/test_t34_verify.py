"""T34 (независимая проверка): нигде в видимом тексте, атрибутах и комментариях нет пометок «проверено / не проверено»;
ссылка «Расскажите, как получилось» одна и живая; заметка разработчика одна, статус дословный; ссылки на compatibility.md живые."""

import re
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "site" / "index.html").as_uri()
ISSUES = "https://github.com/ozerova152-lab/youtube-producer/issues"
FILES = ["README.md", "README.en.md", "site/index.html"]
# любые формы «проверен/не проверяли/tested/untested/verified», «работает в <агент>», «Основной путь», «Рассчитан»
STATUS = re.compile(
    r"проверен|проверено|проверя|не провер|тестировал|tested|untested|verified|unverified|not tried|"
    r"основной путь|рассчитан|полностью|primary path|fully|работает в (claude|codex|cowork)|works (in|with) (claude|codex|cowork)",
    re.IGNORECASE,
)


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", FILES)
def test_no_status_words_anywhere_in_raw_source(rel):
    """Сырой текст файла: видимый текст, атрибуты, HTML-комментарии, meta, alt/title разом.
    Исключение: глагол-просьба «Проверьте» (не пометка)."""
    text = read(rel)
    hits = [m.group(0) for m in STATUS.finditer(text)]
    assert not hits, (rel, hits)


def test_showcase_dom_has_no_status_in_text_or_attributes():
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width in (1000, 360):
            for js in (True, False):
                ctx = b.new_context(viewport={"width": width, "height": 800}, java_script_enabled=js)
                page = ctx.new_page()
                page.goto(PAGE)
                text = page.inner_text("body") + page.content()
                assert not STATUS.findall(text), (width, js, STATUS.findall(text))
                links = page.locator(f'a[href="{ISSUES}"]')
                assert links.count() == 1, (width, js)
                assert links.first.inner_text() == "Расскажите, как получилось"
                assert links.first.is_visible()
                box = links.first.bounding_box()
                assert box and box["width"] > 0 and box["height"] > 0
                if width == 360:
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                # клик действительно кликабелен: элемент не перекрыт
                assert page.evaluate(
                    "href => { const a = document.querySelector('a[href=\"' + href + '\"]'); a.scrollIntoView();"
                    " const r = a.getBoundingClientRect();"
                    " return a.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)) }",
                    ISSUES,
                ), (width, js)
                ctx.close()
        b.close()


def test_issues_link_in_readmes_inside_details_section():
    ru, en = read("README.md"), read("README.en.md")
    ru_sec = ru.split("## Подробнее")[1].split("\n## ")[0]
    en_sec = en.split("\n## More\n")[1].split("\n## ")[0]
    assert f"Расскажите, как получилось: [Issues]({ISSUES})" in ru_sec
    assert en_sec is not None and f"Tell us how it went: [Issues]({ISSUES})" in en_sec


def test_issues_link_is_the_only_feedback_link_on_showcase():
    html = read("site/index.html")
    assert html.count("Расскажите, как получилось") == 1
    assert html.count(ISSUES) == 1


def test_status_note_has_verbatim_old_wording_once():
    old = subprocess.check_output(["git", "show", "HEAD:docs/compatibility.md"], text=True, cwd=ROOT)
    status = old.split("## Статус\n\n")[1].split("\n\n")[0].replace("(chat-mode.md)", "(../chat-mode.md)")
    link = old.split("## Установка по ссылке\n\n")[1].split("\n\n")[0]
    note = read("docs/dev/agent-status.md")
    assert note.count(status) == 1 and note.count(link) == 1


def test_nobody_references_the_note():
    # спека (docs/spec) называет путь заметки как место хранения статуса: это отмечено в журнале T34 как замечание, не ошибка теста
    paths = [ROOT / p for p in ("README.md", "README.en.md", "site/index.html", "AGENTS.md", "CLAUDE.md")]
    paths += list((ROOT / "docs").glob("*.md"))
    paths += list((ROOT / "playbooks").glob("*.md")) + list((ROOT / "docs" / "dev").glob("setup.md"))
    for p in paths:
        assert "agent-status" not in p.read_text(encoding="utf-8"), p


def test_compatibility_keeps_launch_install_covers_key_and_drops_status():
    c = read("docs/compatibility.md")
    for need in ("## Подсказки по агентам", "`claude`", "`codex`", "Claude Desktop",
                 "https://code.claude.com/docs/en/setup", "https://claude.com/download",
                 "https://github.com/openai/codex", "## Обложки залётов (шаг 3б)", "## Про ключ в других агентах",
                 "limits-and-security.md"):
        assert need in c, need
    for gone in ("## Статус", "## Установка по ссылке", "Cowork мы не проверяли", "Codex проверен", "Issues"):
        assert gone not in c, gone


def test_readme_links_and_anchors_to_compatibility_resolve():
    def slug(h):
        h = re.sub(r"[^\w\s-]", "", h.lower().strip())
        return re.sub(r"\s", "-", h)

    c = read("docs/compatibility.md")
    anchors = {slug(m.group(1)) for m in re.finditer(r"^#+\s+(.+)$", c, re.MULTILINE)}
    for rel in ("README.md", "README.en.md"):
        for m in re.finditer(r"compatibility\.md(?:#([^)\s]+))?", read(rel)):
            if m.group(1):
                assert m.group(1) in anchors, (rel, m.group(1), anchors)
    for rel in ("limits-and-security.md", "chat-mode.md"):
        t = read(f"docs/{rel}")
        assert "compatibility.md#" not in t and "Статус по агентам" not in t


def test_readme_shape_kept():
    ru = read("README.md")
    assert len(ru.splitlines()) <= 165
    assert len(re.findall(r"^### Шаг \d", ru, re.MULTILINE)) == 5
