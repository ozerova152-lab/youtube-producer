"""README и AGENTS.md: короткая инструкция для новичка с Windows без WSL (команда, перезагрузка, Ubuntu, дальше)."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def _wsl_block():
    m = re.search(r"^### Windows: как поставить WSL[^\n]*\n(.*?)(?=^### |^## |\Z)", README, re.DOTALL | re.MULTILINE)
    assert m, "нет подраздела «Windows: как поставить WSL» в README"
    return m.group(1)


def test_wsl_block_has_every_step_in_order():
    b = _wsl_block()
    order = ["PowerShell", "от имени администратора", "wsl --install", "Перезагрузите", "Откройте Ubuntu",
             "имя пользователя", "пароль", "sudo apt update && sudo apt install -y git make python3-venv python3-pip",
             "python3 --version", "git clone"]
    pos = [b.find(x) for x in order]
    assert all(p >= 0 for p in pos), dict(zip(order, pos))
    assert pos == sorted(pos), pos


def test_wsl_block_is_short_plain_and_sourced():
    b = _wsl_block()
    assert len(b.splitlines()) < 40
    assert "https://learn.microsoft.com/windows/wsl/install" in b
    assert "Windows 10" in b and "Windows 11" in b
    assert "пароль при вводе не показывается" in b.lower() or "пароль не отображается" in b.lower()
    # дальше всё делается в окне Ubuntu, ZIP на Windows не нужен
    assert "в окне Ubuntu" in b and "ZIP" in b


def test_wsl_block_is_inside_install_section_before_the_three_steps():
    install = README.index("## Установка и запуск")
    assert install < README.index("### Windows: как поставить WSL") < README.index("1. **Скачайте проект")
    assert README.index("### Windows: как поставить WSL") < README.index("### Подсказки по агентам")


def test_troubleshooting_row_for_stuck_wsl_install():
    assert "wsl --install --web-download -d Ubuntu" in README
    assert "0%" in README


def test_agents_md_sends_windows_users_without_wsl_to_readme():
    assert "WSL" in AGENTS and "README" in AGENTS
    assert "не запускай" in AGENTS.lower() or "не выполняй" in AGENTS.lower()


def test_no_personal_data_in_wsl_text():
    b = _wsl_block()
    # общий вид пути («/home/…») допустим, конкретные имена пользователей нет
    assert not re.search(r"/home/[A-Za-z0-9_-]+|matebook|C:\\Users\\[A-Za-z]|/mnt/c/Users/(?!ВАШЕ_ИМЯ)", b)


def test_home_folder_rule_with_reason_and_copy_instructions():
    b = _wsl_block()
    assert "домашней папке Ubuntu" in b and "~/youtube-producer" in b
    assert "/mnt/c" in b and "заблокированные файлы" in b
    assert "может оборваться" in b  # осторожно: «может», а не «всегда»
    # как положить проект: сразу клоном в ~ или копированием из Windows
    assert "cd ~" in b and "git clone https://github.com/ozerova152-lab/youtube-producer.git" in b
    assert "cp -r /mnt/c/Users/ВАШЕ_ИМЯ/Downloads/youtube-producer ~/" in b
    assert "pwd" in b and "это диск Windows" in b
    # в примере нет настоящего имени пользователя
    assert "matebook" not in b


def test_troubleshooting_row_for_project_on_windows_disk():
    row = next(l for l in README.splitlines() if l.startswith("| `make setup` падает, а путь проекта"))
    assert "/mnt/c" in row and "домашнюю папку Ubuntu" in row


def test_agents_md_advises_but_does_not_forbid_windows_disk():
    assert "~/youtube-producer" in AGENTS and "/mnt/" in AGENTS
    assert "тоже работает через WSL" in AGENTS and "надёжнее" in AGENTS
    assert "решает человек" in AGENTS
    assert "`make setup` не запускай" not in AGENTS  # запрета больше нет, только предупреждение


def test_readme_says_windows_disk_works_but_home_folder_is_more_reliable():
    b = _wsl_block()
    assert "Совет для Windows: надёжнее держать проект в домашней папке Ubuntu" in b
    assert "тоже работает через WSL" in b
    assert "остановитесь" not in b
