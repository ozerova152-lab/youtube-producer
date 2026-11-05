"""README.en.md и английская копия инструкции по WSL: по смыслу те же разделы, что в русских файлах; числа, пути и команды совпадают.

T30: статус по агентам, WSL, память месяцев и режим чата вынесены в docs/ (русские; перевод — отдельная задача T31),
поэтому здесь сверяются два README и пара docs/windows-wsl.md ↔ docs/windows-wsl.en.md.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RU = (ROOT / "README.md").read_text(encoding="utf-8")
EN = (ROOT / "README.en.md").read_text(encoding="utf-8")
WSL_RU = (ROOT / "docs/windows-wsl.md").read_text(encoding="utf-8")
WSL_EN = (ROOT / "docs/windows-wsl.en.md").read_text(encoding="utf-8")

# (раздел в README.md, раздел в README.en.md)
SECTION_PAIRS = [
    ("## Что вы получите", "## What you get"),
    ("## Что понадобится", "## What you need"),
    ("## Быстрый старт", "## Quick start"),
    ("### Проверьте, что всё работает", "### Check that everything works"),
    ("## Свой канал", "## Your own channel"),
    ("## Если что-то не получилось", "## If something went wrong"),
    ("## Подробнее", "## More"),
    ("## Лицензия", "## License"),
]
STEP_PAIRS = [
    ("### Шаг 1. Только Windows: поставьте WSL", "### Step 1. Windows only: install WSL"),
    ("### Шаг 2. Скачайте проект", "### Step 2. Download the project"),
    ("### Шаг 3. Проверьте Python и подготовьте проект", "### Step 3. Check Python and prepare the project"),
    ("### Шаг 4. Откройте папку в агенте", "### Step 4. Open the folder in the agent"),
    ("### Шаг 5. Скажите фразу", "### Step 5. Say the phrase"),
]


def _block(text, heading):
    level = heading.split(" ")[0]
    m = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^#{{1,{len(level)}}} |\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, f"нет раздела {heading!r}"
    return m.group(1)


def test_same_sections_in_both_readmes():
    for ru, en in SECTION_PAIRS + STEP_PAIRS:
        assert _block(RU, ru).strip() and _block(EN, en).strip(), (ru, en)


def test_every_step_has_three_parts_in_both_languages():
    for (ru, en) in STEP_PAIRS:
        for text, heading, parts in ((RU, ru, ("**Что сделать:**", "**Что увидите:**", "**Если не получилось:**")),
                                     (EN, en, ("**What to do:**", "**What you will see:**",
                                               "**If it did not work:**"))):
            body = _block(text, heading)
            positions = [body.index(p) for p in parts]
            assert positions == sorted(positions), heading


def test_step3_checks_python_version_first_with_mac_and_ubuntu_advice():
    for text, heading in ((RU, STEP_PAIRS[2][0]), (EN, STEP_PAIRS[2][1])):
        body = _block(text, heading)
        assert body.index("python3 --version") < body.index("make setup")
        assert "python.org/downloads" in body and "3.12" in body
        assert "Mac" in body and "Ubuntu" in body and "Ubuntu-24.04" in body


def test_readmes_are_short_and_have_no_removed_section():
    assert len(RU.splitlines()) <= 165 and len(EN.splitlines()) <= 165
    assert "Сколько времени и подписки" not in RU
    assert "не измерен" not in RU


def test_run_overview_and_cover_files_named_in_both():
    for token in ("00-overview.md", "covers.md", "report.md", "strategy.md", "plan.md"):
        assert token in EN and token in RU, token
    docs_ru = (ROOT / "docs/compatibility.md").read_text(encoding="utf-8")
    for token in ("шаг 3б", "thumbs/", "<id видео>.jpg", "i.ytimg.com"):
        assert token in docs_ru, token


def test_memory_and_chat_docs_keep_statuses_and_numbers():
    memory = (ROOT / "docs/how-it-works.md").read_text(encoding="utf-8")
    for token in ("_v1", "runs/", "report.md", "strategy.md", "briefs/01.md", "`- Статус:`", "отклонён", "позже", "принят"):
        assert token in memory, token
    chat = (ROOT / "docs/chat-mode.md").read_text(encoding="utf-8")
    for token in ("playbooks/no-terminal.md", "docs/import-format.md", "strategy.md", "plan.md", "не больше 60 видео",
                  "5–20"):
        assert token in chat, token


def test_wsl_docs_match_commands_and_numbers():
    for cmd in ("wsl --install", "sudo apt update && sudo apt install -y git make python3-venv python3-pip",
                "python3 --version", "3.12", "wsl --install --web-download -d Ubuntu", "wsl --install -d Ubuntu-24.04",
                "/mnt/c", "~/youtube-producer", "pwd"):
        assert cmd in WSL_EN and cmd in WSL_RU, cmd
    assert "20-30 minutes" in WSL_EN and "20–30 минут" in WSL_RU
    assert "Я на Windows и ничего не понимаю в терминале" in WSL_RU
    assert "I am on Windows and understand nothing about the terminal" in WSL_EN
    assert "windows-wsl.md" in RU and "windows-wsl.en.md" in EN and "windows-wsl.en.md" not in RU


def test_every_command_and_path_in_english_readme_exists_in_russian_or_repo():
    spans = re.findall(r"`([^`\n]+)`", EN)
    to_ru = {"<channel>": "<канал>", "<run>": "<запуск>", "<video id>": "<id видео>",
             "<month>_<segment>_v<N>": "<месяц>_<сегмент>_v<N>"}
    command = re.compile(r"^(make |\.venv/|wsl |sudo |cd |cp |pwd|git |python3|mkdir )")
    # английский README вправе упомянуть команду из английской копии WSL
    allowed_text = RU + WSL_RU + (ROOT / "docs/compatibility.md").read_text(encoding="utf-8")
    for span in set(spans):
        if command.match(span):
            span = span.replace("<channel>", "<канал>")
            assert span in allowed_text, f"команды {span!r} нет в README.md"
        elif "/" in span and not span.startswith(("http", "~", "/", "<")) and "*" not in span and " " not in span:
            path = span.rstrip("/")
            if "<" in path:
                for en_word, ru_word in to_ru.items():
                    span = span.replace(en_word, ru_word)
                assert span in allowed_text, f"шаблона пути {span!r} нет в README.md"
            else:
                assert (ROOT / path).exists() or span in RU, f"пути {span!r} нет"


def test_fenced_commands_match_russian():
    en_blocks = re.findall(r"```bash\n(.*?)```", EN, re.DOTALL)
    assert en_blocks
    for block in en_blocks:
        for line in block.splitlines():
            if line.strip():
                # перевод только заготовок в угловых скобках и примера пути; команды совпадают дословно
                ru_line = line.strip().replace("<channel>", "<канал>").replace("path/to/file.csv", "путь/к/файлу.csv")
                assert ru_line in RU or ru_line == "cd youtube-producer", line
    # три команды демо идут в том же порядке
    ru_demo = _block(RU, "### Проверьте, что всё работает")
    en_demo = _block(EN, "### Check that everything works")
    ru_cmds = re.findall(r"```bash\n(.*?)```", ru_demo, re.DOTALL)[0].strip().splitlines()
    en_cmds = re.findall(r"```bash\n(.*?)```", en_demo, re.DOTALL)[0].strip().splitlines()
    assert ru_cmds == en_cmds and len(ru_cmds) == 3


def test_numbers_match():
    assert "10,000" in EN and "10 000" in RU
    assert "3.12" in EN and "3.12" in RU
    assert "11 videos and 2 channels" in EN and "11 видео, 2 канала" in RU


def test_english_readme_does_not_restate_status_but_points_to_it():
    # статус по агентам живёт один раз, в docs/compatibility.md (T30); английский README только ссылается на него
    assert "docs/compatibility.md" in EN
    assert not re.search(r"fully tested|was tested on a real channel", EN)
    assert not re.search(r"Cowork[^.\n]{0,40}(is|was) (fully )?tested", EN)


def test_english_readme_has_no_keys_and_links_alive():
    assert not re.search(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}", EN)
    for text, base in ((EN, ROOT), (WSL_EN, ROOT / "docs")):
        for rel in re.findall(r"\]\((?!https?:|#)([^)\s]+)\)", text):
            path = rel.split("#")[0]
            if path:
                assert (base / path).exists(), rel
