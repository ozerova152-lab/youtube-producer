"""Неожиданный сбой не печатает локальные переменные: в них бывает ключ YouTube.

Настоящий процесс, а не CliRunner: красивый трейсбэк Typer выводит только вне тестового раннера.
"""

import subprocess
import sys

CANARY = "CANARY-KEY-do-not-leak-4b1e82"

# Ключ собирается из двух кусков: даже если строка кода попадёт в вывод, целиком её там не будет.
SCRIPT = """
import produce.cli as cli


def boom(*args, **kwargs):
    key = "CANARY-KEY-" + "do-not-leak-4b1e82"
    raise RuntimeError("неожиданный сбой")


cli._collect = boom
cli.app()
"""


def test_unexpected_crash_does_not_print_locals(tmp_path):
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT, "--channel", str(tmp_path), "collect"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    output = done.stdout + done.stderr
    assert done.returncode != 0
    assert "неожиданный сбой" in output  # сбой реально напечатан, тест не пустой
    assert CANARY not in output
