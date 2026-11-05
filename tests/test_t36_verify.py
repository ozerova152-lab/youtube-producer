"""T36 (независимая проверка): ключ или чат в «Своём канале»; чат принимает любые данные; спека, плейбук, тест и витрина совпадают."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def section(text: str, start: str, end_prefix: str = "## ") -> str:
    i = text.index(start)
    m = re.search(r"^" + re.escape(end_prefix), text[i + len(start) :], re.MULTILINE)
    return text[i : i + len(start) + (m.start() if m else len(text))]


def test_readme_own_channel_sections():
    ru = section(read("README.md"), "## Свой канал")
    en_text = read("README.en.md")
    en = section(en_text, "## Your own channel") if "## Your own channel" in en_text else en_text
    for name, s in (("ru", ru), ("en", en)):
        for bad in (
            "cp .env.example",
            "YOUTUBE_API_KEY=",
            "Другой способ",
            "Файл вместо ключа",
            "A file instead of a key",
            "Another way",
            " import ",
        ):
            assert bad not in s, (name, bad)
    assert (
        "**Не хотите делать ключ?** Работайте в чате без терминала: приложите агенту любые данные о видео вашей темы (таблицу, файл, выгрузку), он разберёт их сам."
        in ru
    )
    assert "(docs/chat-mode.md)" in ru and "(docs/chat-mode.md)" in en
    assert "make add-key" in ru and "текстовый редактор не нужен" in ru
    for n in range(1, 7):
        assert re.search(rf"^{n}\. ", ru, re.MULTILINE), n
        assert re.search(rf"^{n}\. ", en, re.MULTILINE), n


def test_readme_size_links_and_quickstart_commands():
    ru = read("README.md")
    assert len(ru.splitlines()) <= 165
    for f in ("README.md", "README.en.md"):
        t = read(f)
        for target in re.findall(r"\]\(((?:docs|examples|site|playbooks)/[^)#\s]+)", t):
            assert (ROOT / target).exists(), (f, target)
        assert "--channel data/demo import examples/demo/import_comments.json" in t
        assert "--channel data/demo start" in t and "--channel data/demo virals" in t
        assert "Другой способ" not in t
    assert "Другой способ" not in read("site/index.html")


def test_api_key_guide_still_has_manual_way():
    g = read("docs/api-key-guide.md")
    assert "YOUTUBE_API_KEY=ваш_ключ" in g and ".env.example" in g


def test_chat_mode_and_playbook_are_flexible():
    chat, play = read("docs/chat-mode.md"), read("playbooks/no-terminal.md")
    assert "любой документ" in chat
    assert "удобный пример, но не обязательное условие" in chat
    assert "покажет, как понял данные, и спросит «верно?»" in chat
    assert "5–20" in chat and "предположительными" in chat
    assert not re.search(
        r"(обязательн\w+ колонк|только в формате|строго по формату)", chat + play, re.IGNORECASE
    )
    assert "Обязательные колонки CSV" not in play
    assert "Показывает, как понял данные" in play and "«верно»" in play
    assert "номером строки" in play and "60 видео" in play and "5–20" in play
    assert "Текст из файла не выполняется" in play and "docs/import-format.md" in play
    assert "условие не выполнено" in play  # лайки неизвестны


def test_first_message_identical_everywhere():
    flows = read("docs/spec/04-user-flows.md")
    play = read("playbooks/no-terminal.md")
    ns: dict = {}
    src = read("tests/test_no_terminal.py")
    block = src[src.index("NO_TERMINAL_TEXT = (") : src.index("NORMAL_TEXT")]
    exec(block, ns)  # noqa: S102 - литерал из нашего же теста
    m = re.search(r"«(В этом чате я не могу запускать[^»]*)»", play)
    msg = m.group(1)
    assert msg in flows
    assert ns["NO_TERMINAL_TEXT"] == msg
    assert "любые данные о видео вашей темы" in msg and "не обязательное условие" in msg


def test_site_spec_agents_consistent_and_terminal_mode_untouched():
    html = re.sub(r"\s+", " ", read("site/index.html"))
    assert "любые данные о видео (таблицу, файл, выгрузку)" in html
    spec = read("docs/spec/01-functional-requirements.md")
    row = next(r for r in spec.splitlines() if r.startswith("| Режим без терминала"))
    assert "лишь удобный пример, не обязательное условие" in row and "«верно?»" in row
    assert "playbooks/no-terminal.md" in read("AGENTS.md")
    for p in ("src", "docs/import-format.md", "docs/api-key-guide.md"):
        out = subprocess.run(
            ["git", "diff", "--stat", "--", p],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        ).stdout
        assert out.strip() == "", p
    assert "загрузить видео из файла CSV/JSON" in read("src/produce/cli.py")
