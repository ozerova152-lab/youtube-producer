"""T36: в «Своём канале» ключ или чат; ручной `.env` и импорт файлом ушли из README; режим чата принимает любые данные."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RU = (ROOT / "README.md").read_text(encoding="utf-8")
EN = (ROOT / "README.en.md").read_text(encoding="utf-8")
CHAT = (ROOT / "docs" / "chat-mode.md").read_text(encoding="utf-8")
PLAY = (ROOT / "playbooks" / "no-terminal.md").read_text(encoding="utf-8")
HTML = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
GUIDE = (ROOT / "docs" / "api-key-guide.md").read_text(encoding="utf-8")
PHRASE = ("**Не хотите делать ключ?** Работайте в чате без терминала: приложите агенту любые данные о видео "
          "вашей темы (таблицу, файл, выгрузку), он разберёт их сам.")


def test_readmes_lost_manual_env_and_file_import_blocks():
    for name, text in (("README.md", RU), ("README.en.md", EN)):
        assert "cp .env.example" not in text and "YOUTUBE_API_KEY=" not in text, name
        # команда импорта пользовательского файла ушла; три команды проверки на data/demo остаются
        assert not re.search(r"--channel data/<(канал|channel)>[^\n]*\simport\s", text), name
        assert "Другой способ" not in text and "Файл вместо ключа" not in text, name
        assert "A file instead of a key" not in text and "path/to/file.csv" not in text, name


def test_new_phrase_links_to_chat_mode_doc():
    assert PHRASE in RU
    assert "[Как это устроено](docs/chat-mode.md)" in RU
    assert "Don't want to make a key?" in EN and "docs/chat-mode.md" in EN
    # шаги ключа и «текстовый редактор не нужен» на месте, ручной способ остался в инструкции по ключу
    assert "make add-key" in RU and "текстовый редактор не нужен" in RU
    assert "YOUTUBE_API_KEY=ваш_ключ" in GUIDE and ".env.example" in GUIDE


def test_chat_mode_accepts_any_document_and_format_is_an_example():
    assert "любой документ" in CHAT and "названия видео, просмотры и даты" in CHAT
    assert "удобный пример, но не обязательное условие" in CHAT
    assert "покажет, как понял данные, и спросит «верно?»" in CHAT
    assert "5–20" in CHAT and "предположительными" in CHAT


def test_playbook_is_not_strict_and_has_understanding_check():
    assert "не обязательное условие" in PLAY and "docs/import-format.md" in PLAY
    assert "Показывает, как понял данные" in PLAY and "«верно»" in PLAY
    assert "Обязательные колонки CSV" not in PLAY
    assert "5–20" in PLAY and "номером строки" in PLAY
    assert "по формату из `docs/import-format.md`" not in PLAY


def test_showcase_chat_block_is_consistent():
    assert "любые данные о видео (таблицу, файл, выгрузку)" in HTML
    assert "import" not in re.sub(r"<[^>]+>", "", HTML).lower()


def test_terminal_mode_import_path_is_left_alone():
    cli = (ROOT / "src" / "produce" / "cli.py").read_text(encoding="utf-8")
    assert "загрузить видео из файла CSV/JSON" in cli
