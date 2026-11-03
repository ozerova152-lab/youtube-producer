"""README.en.md: по смыслу те же разделы, что в README.md; числа, пути и команды совпадают; статус совместимости тот же."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RU = (ROOT / "README.md").read_text(encoding="utf-8")
EN = (ROOT / "README.en.md").read_text(encoding="utf-8")

# (раздел в README.md, раздел в README.en.md)
SECTION_PAIRS = [
    ("## Что это и что вы получите", "## What you get"),
    ("## Как проект помнит прошлые месяцы", "## How the project remembers past months"),
    ("### Windows: как поставить WSL (один раз)", "### Windows: how to install WSL (once)"),
    ("### Подсказки по агентам", "### Agents"),
    ("## Если у вас только чат", "## If you only have a chat"),
    ("## Если что-то не получилось", "## If something went wrong"),
    ("## Для чего проект не подходит и ограничения", "## Limitations"),
]


def _block(text, heading):
    level = heading.split(" ")[0]
    m = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^#{{1,{len(level)}}} |\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, f"нет раздела {heading!r}"
    return m.group(1)


def test_same_sections_in_both_readmes():
    for ru, en in SECTION_PAIRS:
        assert _block(RU, ru).strip() and _block(EN, en).strip(), (ru, en)


def test_run_overview_cover_analysis_and_thumbs_described():
    for token in ("00-overview.md", "covers.md", "step 3b", "thumbs/", "<video id>.jpg"):
        assert token in EN, token
    for token in ("00-overview.md", "covers.md", "шаг 3б", "thumbs/", "<id видео>.jpg"):
        assert token in RU, token
    assert "i.ytimg.com" in EN and "i.ytimg.com" in RU
    assert "Claude Code" in _block(EN, "### Agents").split("Cover analysis (step 3b)")[1]


def test_memory_section_mentions_same_statuses_and_paths():
    en = _block(EN, "## How the project remembers past months")
    ru = _block(RU, "## Как проект помнит прошлые месяцы")
    for path in re.findall(r"[\w\-]+_v\d|runs/|report\.md|strategy\.md|briefs/01\.md", ru):
        assert path in en, path
    assert "rejected" in en and "later" in en and "accepted" in en
    assert "`- Статус:`" in en and "`- Статус:`" in ru  # строка из шаблона брифа не переводится


def test_chat_mode_section_matches_russian_numbers_and_paths():
    en = _block(EN, "## If you only have a chat")
    ru = _block(RU, "## Если у вас только чат")
    for path in ("playbooks/no-terminal.md", "docs/import-format.md", "strategy.md", "plan.md"):
        assert path in en and path in ru, path
    assert "60 videos" in en and "не больше 60 видео" in ru
    assert "5-20" in en and "5–20" in ru


def test_wsl_section_matches_russian_commands_and_numbers():
    en = _block(EN, "### Windows: how to install WSL (once)")
    ru = _block(RU, "### Windows: как поставить WSL (один раз)")
    for cmd in ("wsl --install", "sudo apt update && sudo apt install -y git make python3-venv python3-pip",
                "python3 --version", "3.12"):
        assert cmd in en and cmd in ru, cmd
    assert "20-30 minutes" in en and "20–30 минут" in ru
    assert "/mnt/c" in EN and "/mnt/c" in RU and "~/youtube-producer" in EN


def test_every_command_and_path_in_english_readme_exists_in_russian_or_repo():
    spans = re.findall(r"`([^`\n]+)`", EN)
    to_ru = {"<channel>": "<канал>", "<run>": "<запуск>", "<video id>": "<id видео>",
             "<month>_<segment>_v<N>": "<месяц>_<сегмент>_v<N>"}
    command = re.compile(r"^(make |\.venv/|wsl |sudo |cd |cp |pwd|git |python3|mkdir )")
    for span in set(spans):
        if command.match(span):
            assert span in RU, f"команды {span!r} нет в README.md"
        elif "/" in span and not span.startswith(("http", "~", "/", "<")) and "*" not in span and " " not in span:
            path = span.rstrip("/")
            if "<" in path:
                for en_word, ru_word in to_ru.items():
                    span = span.replace(en_word, ru_word)
                assert span in RU, f"шаблона пути {span!r} нет в README.md"
            else:
                assert (ROOT / path).exists() or span in RU, f"пути {span!r} нет"


def test_fenced_commands_match_russian():
    en_blocks = re.findall(r"```bash\n(.*?)```", EN, re.DOTALL)
    ru_text = RU
    for block in en_blocks:
        for line in block.splitlines():
            if line.strip():
                assert line.strip() in ru_text or line.strip() == "cd youtube-producer", line


def test_numbers_match():
    assert "10,000 units" in EN and "10 000 единиц" in RU
    assert "120 MB" in EN and "120 МБ" in RU
    assert "3.12" in EN and "3.12" in RU
    assert "30 Oct 2026" in EN and "30.10.2026" in RU
    assert "11 videos and 2 channels" in EN and "11 видео, 2 канала" in RU


def test_compatibility_status_is_same_and_not_overstated():
    # то, что проверено: только Claude Code (полностью) и Codex (30.10.2026, установка → брифы)
    assert "main path is claude code, fully tested" in EN.lower()
    assert "Codex was tested on a real channel (30 Oct 2026) from setup to briefs" in EN
    assert "We did not test Cowork" in EN
    assert "has not been tested on a real channel" in EN  # обычный чат без терминала
    assert "playbooks/no-terminal.md" in EN
    # то же в русском README
    assert "Cowork мы не проверяли" in RU and "Обычный чат без терминала" in RU
    # Cowork и чат нигде не названы проверенными
    for m in re.finditer(r"(Cowork|chat)[^.\n]{0,60}(tested|verified)", EN):
        assert re.search(r"not|did not|never|un", m.group(0)), m.group(0)
    assert not re.search(r"Cowork[^.\n]{0,40}(is|was) (fully )?tested", EN)
    # «fully tested» сказано только про Claude Code
    for m in re.finditer(r"fully tested", EN):
        assert "Claude Code" in EN[max(0, m.start() - 120):m.start()], EN[m.start() - 60:m.end()]


def test_english_readme_has_no_keys_and_links_alive():
    assert not re.search(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}", EN)
    for rel in re.findall(r"\]\((?!https?:|#)([^)\s]+)\)", EN):
        assert (ROOT / rel).exists(), rel
