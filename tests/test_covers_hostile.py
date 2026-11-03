"""T25 (независимая проверка): враждебные случаи `check-files --step covers`."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app

ROOT = Path(__file__).parent.parent
EXPECTED = DEMO / "expected"
GOOD = (EXPECTED / "covers.md").read_text("utf-8")
NONE = (EXPECTED / "covers_no_data.md").read_text("utf-8")


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def invoke(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args, "--segment", "ru"])


@pytest.fixture
def run(channel):
    assert invoke(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    assert invoke(channel, "virals").exit_code == 0
    return max((channel / "runs").iterdir())


def red(channel, run, text, *needles):
    (run / "covers.md").write_text(text, "utf-8")
    res = invoke(channel, "check-files", "--step", "covers")
    assert res.exit_code == 1, res.output
    assert "covers.md" in res.output
    for n in needles:
        assert n in res.output, (n, res.output)
    return res.output


def test_virals_json_missing(channel, run):
    (run / "virals.json").unlink()
    (run / "covers.md").write_text(GOOD, "utf-8")
    res = invoke(channel, "check-files", "--step", "covers")
    assert res.exit_code == 1 and "Traceback" not in res.output


def test_virals_json_broken(channel, run):
    (run / "virals.json").write_text("{не json", "utf-8")
    (run / "covers.md").write_text(GOOD, "utf-8")
    res = invoke(channel, "check-files", "--step", "covers")
    assert res.exit_code == 1 and "Traceback" not in res.output


def test_empty_virals_with_blocks_is_red(channel, run):
    (run / "virals.json").write_text(json.dumps({"virals": []}), "utf-8")
    red(channel, run, GOOD, "не залёт")


def test_empty_file(channel, run):
    red(channel, run, "", "Основа разбора")


def test_not_utf8(channel, run):
    (run / "covers.md").write_bytes("Разбор".encode("cp1251"))
    res = invoke(channel, "check-files", "--step", "covers")
    assert res.exit_code == 1 and "Traceback" not in res.output


def test_none_mode_with_blocks_or_without_reason(channel, run):
    red(channel, run, NONE + "\n" + GOOD.split("## Залёт 1", 1)[1].join(["## Залёт 1", ""]), "блоки залётов")
    red(channel, run, NONE.replace("Причина: человек выбрал «пропустить»", "Причина: <почему>"), "Причина")
    red(channel, run, NONE.replace("Причина: человек выбрал «пропустить»", "Причина:"), "Причина")


def test_none_mode_without_guess_note(channel, run):
    red(channel, run, re.sub(r"^> .*\n", "", NONE, flags=re.MULTILINE), "предположение агента")


def test_fake_foreign_id_and_traversal(channel, run):
    red(channel, run, GOOD.replace("Видео: demo_v07", "Видео: ../../etc/passwd"), "не залёт")
    red(channel, run, GOOD.replace("Видео: demo_v07", "Видео: DEMO_V07"), "не залёт")


def test_norm_not_number_and_template_summary(channel, run):
    red(channel, run, GOOD.replace("К норме канала: 4.39", "К норме канала: много"), "нужно число")
    red(channel, run, GOOD.replace("У обеих обложек одна крупная мысль и мало элементов; текст короткий и читается без увеличения.", "<что повторяется>"), "Общие закономерности")


def test_empty_summary_sections(channel, run):
    t = re.sub(r"(## Общие закономерности\n)\n.*\n", r"\1\n", GOOD)
    red(channel, run, t, "Общие закономерности")


def test_missing_mode_field(channel, run):
    red(channel, run, GOOD.replace("- Основа разбора: обложки по ссылкам\n", ""), "Основа разбора")


def test_folder_mode_with_non_image_file_only(channel, run):
    (run / "thumbs").mkdir()
    (run / "thumbs" / "notes.txt").write_text("x")
    red(channel, run, GOOD.replace("обложки по ссылкам", "обложки из папки thumbs"), "нет картинок")


def test_folder_mode_uppercase_suffix_ok(channel, run):
    (run / "thumbs").mkdir()
    (run / "thumbs" / "demo_v01.JPG").write_bytes(b"x")
    (run / "covers.md").write_text(GOOD.replace("обложки по ссылкам", "обложки из папки thumbs"), "utf-8")
    assert invoke(channel, "check-files", "--step", "covers").exit_code == 0


def test_check_does_not_touch_settings_or_run_json(channel, run):
    s = (channel / "settings.yaml").read_bytes()
    r = (run / "run.json").read_bytes()
    (run / "covers.md").write_text(GOOD, "utf-8")
    assert invoke(channel, "check-files", "--step", "covers").exit_code == 0
    assert (channel / "settings.yaml").read_bytes() == s and (run / "run.json").read_bytes() == r


def test_flow_and_check_messages_match_spec_verbatim():
    spec = (ROOT / "docs/spec/04-user-flows.md").read_text("utf-8")
    cli = (ROOT / "src/produce/cli.py").read_text("utf-8")
    assert "Проверено: разбор обложек пропущен (нет данных), ошибок нет" in spec and "Проверено: разбор обложек пропущен (нет данных), ошибок нет" in cli
    assert "Проверено: разбор обложек по 8 залётам, ошибок нет" in spec
    play = (ROOT / "playbooks/03b-covers.md").read_text("utf-8")
    for phrase in ("Я не могу открыть обложки по ссылкам (или ссылок на обложки в этом запуске нет). Скачайте обложки залётов и положите их в `data/<канал>/runs/<запуск>/thumbs/` под именем `<id видео>.jpg` (подходят jpg, png, webp). Нужны видео: <id>, <id>. Когда будет готово, напишите «готово». Если обложки разбирать не хотите, напишите «пропустить»",
                   "Нет картинок для: <id>. Положите их и напишите «готово» или напишите «пропустить»",
                   "Хорошо, обложки пропускаю. Иду к нише"):
        assert phrase in spec and phrase in play, phrase


def test_only_ytimg_host_allowed_in_playbook():
    play = (ROOT / "playbooks/03b-covers.md").read_text("utf-8")
    hosts = set(re.findall(r"https?://[^/\s`»)]+", play))
    assert hosts == {"https://i.ytimg.com"}, hosts


def test_playbook_hostile_text_rule_and_no_stage_move():
    play = (ROOT / "playbooks/03b-covers.md").read_text("utf-8")
    assert "статусы не ставятся" in play and "`settings.yaml` не трогается" in play
    assert "Без «готово» или «пропустить» шаг дальше не идёт" in play


def test_docs_consistent_across_files():
    for rel in ("README.md", "playbooks/README.md", "templates/README.md", "playbooks/00-month.md", "AGENTS.md"):
        t = (ROOT / rel).read_text("utf-8")
        assert "covers" in t or "обложк" in t, rel
