"""`make add-key` / `produce add-key`: ключ вносится без редактора, значение не показывается и не логируется."""

import logging
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from produce import cli
from produce.cli import app
from produce.core.errors import ProduceError
from produce.core.settings import load_api_key, save_api_key

ROOT = Path(__file__).parent.parent
CANARY = "CANARY-KEY-" + "do-not-leak-4b1e82"
OTHER = "CANARY-KEY-" + "other-9c7d11"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _run(monkeypatch, tmp_path, inputs, *, tty=True, extra_input=""):
    """Запускает `produce add-key --env-file <tmp>/.env`; inputs — что вернёт скрытый ввод."""
    answers = iter(inputs)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: tty)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    env = tmp_path / ".env"
    result = CliRunner().invoke(app, ["add-key", "--env-file", str(env)], input=extra_input)
    return env, result


# --- ядро ---------------------------------------------------------------------------------

def test_save_creates_env_with_owner_only_permissions(tmp_path):
    env = tmp_path / ".env"
    replaced = save_api_key(CANARY, env)
    assert replaced is False
    assert env.read_text(encoding="utf-8") == f"YOUTUBE_API_KEY={CANARY}\n"
    assert _mode(env) == 0o600
    assert load_api_key(env) == CANARY
    assert not list(tmp_path.glob(".*.tmp"))  # временных файлов не осталось


def test_save_replaces_only_the_key_line_and_fixes_wide_permissions(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"# мой файл\nOTHER=1\nYOUTUBE_API_KEY={OTHER}\nTAIL=2\n", encoding="utf-8")
    env.chmod(0o644)
    replaced = save_api_key(CANARY, env)
    assert replaced is True
    assert env.read_text(encoding="utf-8") == f"# мой файл\nOTHER=1\nYOUTUBE_API_KEY={CANARY}\nTAIL=2\n"
    assert _mode(env) == 0o600


def test_save_appends_key_when_file_has_no_key_line(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OTHER=1", encoding="utf-8")
    assert save_api_key(CANARY, env) is False
    assert env.read_text(encoding="utf-8") == f"OTHER=1\nYOUTUBE_API_KEY={CANARY}\n"


@pytest.mark.parametrize("bad", ["", "   ", "two words", "with\ttab", 'quo"te', "sing'le", "line\nbreak"])
def test_save_rejects_bad_values_without_echoing_them(tmp_path, bad):
    env = tmp_path / ".env"
    with pytest.raises(ProduceError) as err:
        save_api_key(bad, env)
    assert "не записан" in str(err.value)
    if bad.strip():
        assert bad not in str(err.value)
    assert not env.exists()


# --- команда -------------------------------------------------------------------------------

def test_add_key_writes_env_and_never_prints_the_value(monkeypatch, tmp_path, caplog):
    with caplog.at_level(logging.DEBUG):
        env, result = _run(monkeypatch, tmp_path, [CANARY, CANARY])
    assert result.exit_code == 0, result.output
    assert CANARY not in result.output
    assert CANARY not in caplog.text
    assert "Ключ записан в" in result.output and "только для владельца" in result.output
    assert env.read_text(encoding="utf-8") == f"YOUTUBE_API_KEY={CANARY}\n"
    assert _mode(env) == 0o600


def test_add_key_mismatch_writes_nothing(monkeypatch, tmp_path):
    env, result = _run(monkeypatch, tmp_path, [CANARY, OTHER])
    assert result.exit_code == 1
    assert "Два ввода не совпали, ключ не записан" in result.output
    assert CANARY not in result.output and OTHER not in result.output
    assert not env.exists()


def test_add_key_empty_or_spaces_is_refused(monkeypatch, tmp_path):
    env, result = _run(monkeypatch, tmp_path, ["two words", "two words"])
    assert result.exit_code == 1
    assert "Ключ пустой или в нём есть пробелы или кавычки. Ключ не записан" in result.output
    assert "two words" not in result.output
    assert not env.exists()


def test_add_key_without_terminal_refuses_and_writes_nothing(monkeypatch, tmp_path):
    env, result = _run(monkeypatch, tmp_path, [CANARY, CANARY], tty=False)
    assert result.exit_code == 1
    assert "Ключ вводят в обычном терминале" in result.output and "make add-key" in result.output
    assert CANARY not in result.output
    assert not env.exists()


def test_add_key_existing_key_asks_and_default_is_no(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"YOUTUBE_API_KEY={OTHER}\n", encoding="utf-8")
    _, result = _run(monkeypatch, tmp_path, [CANARY, CANARY], extra_input="\n")
    assert result.exit_code == 0
    assert "Ключ уже записан в" in result.output and "Ключ не изменён" in result.output
    assert OTHER not in result.output  # существующий ключ тоже не показывается
    assert env.read_text(encoding="utf-8") == f"YOUTUBE_API_KEY={OTHER}\n"


def test_add_key_existing_key_replaced_after_yes(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"YOUTUBE_API_KEY={OTHER}\n", encoding="utf-8")
    _, result = _run(monkeypatch, tmp_path, [CANARY, CANARY], extra_input="y\n")
    assert result.exit_code == 0
    assert env.read_text(encoding="utf-8") == f"YOUTUBE_API_KEY={CANARY}\n"
    assert CANARY not in result.output and OTHER not in result.output


def test_add_key_cancel_does_not_write(monkeypatch, tmp_path):
    def boom(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(cli.getpass, "getpass", boom)
    env = tmp_path / ".env"
    result = CliRunner().invoke(app, ["add-key", "--env-file", str(env)])
    assert result.exit_code == 1 and "Ввод отменён, ключ не записан" in result.output
    assert not env.exists()


def test_add_key_write_failure_message_has_no_value(monkeypatch, tmp_path):
    def broken(value, env_path):
        raise OSError(f"disk error while writing {value}")

    monkeypatch.setattr(cli, "save_api_key", broken)
    _, result = _run(monkeypatch, tmp_path, [CANARY, CANARY])
    assert result.exit_code == 1
    assert CANARY not in result.output
    assert CANARY not in repr(result.exception)


def test_missing_key_message_points_to_make_add_key():
    src = (ROOT / "src/produce/cli.py").read_text(encoding="utf-8")
    assert src.count("записать его командой `make add-key`") == 2
    assert "положить его в файл `.env` строкой" not in src


# --- make ----------------------------------------------------------------------------------

def test_make_add_key_target_exists_and_is_not_part_of_check():
    out = subprocess.run(["make", "-n", "add-key"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert ".venv/bin/produce add-key" in out
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "add-key" in makefile.split(".PHONY:")[1].splitlines()[0]
    check_line = next(l for l in makefile.splitlines() if l.startswith("check:"))
    assert "add-key" not in check_line


def test_make_add_key_refuses_without_terminal_in_a_real_process(tmp_path):
    # настоящий процесс без терминала (как команда, запущенная агентом): ничего не пишет и не просит ввод
    env = tmp_path / ".env"
    produce = ROOT / ".venv" / "bin" / "produce"
    if not produce.exists():
        pytest.skip("нет .venv/bin/produce")
    p = subprocess.run([str(produce), "add-key", "--env-file", str(env)], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30, cwd=tmp_path, check=False,
                       env={**os.environ, "COLUMNS": "200"})
    assert p.returncode == 1
    assert "Ключ вводят в обычном терминале" in p.stdout + p.stderr
    assert not env.exists()


# --- настоящий терминал: ввод скрыт, права 0600 ----------------------------------------------

def test_real_terminal_hides_input_and_sets_permissions(tmp_path):
    pty = pytest.importorskip("pty")
    produce = ROOT / ".venv" / "bin" / "produce"
    if not produce.exists():
        pytest.skip("нет .venv/bin/produce")
    env_file = tmp_path / ".env"
    pid, fd = pty.fork()
    if pid == 0:  # дочерний процесс: настоящий терминал вместо stdin/stdout
        os.chdir(tmp_path)
        os.execv(str(produce), [str(produce), "add-key", "--env-file", str(env_file)])
    out = b""

    def read_until(marker: bytes) -> None:
        nonlocal out
        while marker not in out:
            chunk = os.read(fd, 4096)
            if not chunk:
                raise AssertionError(f"процесс завершился, не дождавшись {marker!r}: {out!r}")
            out += chunk

    try:
        read_until("Вставьте ключ YouTube".encode())
        read_until(b": ")
        os.write(fd, (CANARY + "\n").encode())
        read_until("Повторите ключ".encode())
        read_until(b": ")
        os.write(fd, (CANARY + "\n").encode())
        read_until("Значение не показывается".encode())
    finally:
        _, status = os.waitpid(pid, 0)
        os.close(fd)
    assert os.WEXITSTATUS(status) == 0
    assert CANARY.encode() not in out  # терминал не показал введённое
    assert env_file.read_text(encoding="utf-8") == f"YOUTUBE_API_KEY={CANARY}\n"
    assert _mode(env_file) == 0o600


# --- тексты: команда названа везде, привязки к редактору нет --------------------------------

def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_docs_name_make_add_key_and_have_no_editor_binding():
    for name in ("README.md", "AGENTS.md", "docs/api-key-guide.md"):
        text = _read(name)
        assert "make add-key" in text, name
        assert not re.search(r"vs ?code|visual studio", text, re.IGNORECASE), name
        assert "code ." not in text, name
    guide = _read("docs/api-key-guide.md")
    assert guide.index("Способ 1") < guide.index("Способ 2")
    assert "редактор не нужен" in guide
    assert "Не запускайте её из окна чата с агентом" in guide
    readme = _read("README.md")
    assert "текстовый редактор не нужен" in readme


def test_agents_md_forbids_asking_for_key_or_running_add_key():
    agents = _read("AGENTS.md")
    assert "make add-key" in agents
    assert "Не проси ключ в чате" in agents and "не запускай `make add-key` сам" in agents


def test_playbook_and_skill_point_to_add_key():
    assert "make add-key" in _read("playbooks/01-collect.md")
    assert "make add-key" in _read("playbooks/00-month.md")
    assert "make add-key" in _read(".claude/skills/setup-check/SKILL.md")
