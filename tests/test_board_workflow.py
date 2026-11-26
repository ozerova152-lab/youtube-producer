"""Agent and board exchange through public CLI on an isolated demo channel."""

import json

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.board import BoardStore
from produce.cli import app

RUN = "2026-10_ru_v1"


@pytest.fixture
def prepared(channel, monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    cli = CliRunner()
    for args in (("import", str(DEMO / "import_comments.json")), ("virals",)):
        result = cli.invoke(app, ["--channel", str(channel), *args, "--segment", "ru"])
        assert result.exit_code == 0, result.output
    run = channel / "runs" / RUN
    strategy = (DEMO / "expected" / "strategy.md").read_text(encoding="utf-8")
    (run / "strategy.md").write_text(strategy.replace("Статус: черновик", "Статус: утверждена"), encoding="utf-8")
    return channel, run


def call(channel, *args, input=None):
    return CliRunner().invoke(app, ["--channel", str(channel), *args, "--segment", "ru"], input=input)


def test_agent_can_save_ideas_without_changing_human_decisions(prepared):
    channel, _run = prepared
    draft = {"revision": None, "ideas": [{"id": "idea-1", "title": "Тема", "source": "report.md", "status": ""}]}
    response = call(channel, "ideas-save", input=json.dumps(draft, ensure_ascii=False))
    assert response.exit_code == 0, response.output
    store = BoardStore(channel.parent)
    snap = store.snapshot(channel.name, RUN)
    assert snap["ideas"][0]["status"] == ""
    store.decide(channel.name, RUN, "idea", "idea-1", "принят", snap["ideas_revision"])
    response = call(channel, "ideas-save", input=json.dumps(draft, ensure_ascii=False))
    assert response.exit_code == 1
    assert store.snapshot(channel.name, RUN)["ideas"][0]["status"] == "принят"


def test_approved_ideas_have_exactly_one_brief_and_old_checks_remain(prepared):
    channel, run = prepared
    store = BoardStore(channel.parent)
    ideas = [{"id": "good", "title": "Первая", "source": "report.md", "status": ""},
             {"id": "no", "title": "Вторая", "source": "report.md", "status": ""}]
    store.save_ideas(channel.name, RUN, ideas, None)
    snap = store.snapshot(channel.name, RUN)
    store.decide(channel.name, RUN, "idea", "good", "принят", snap["ideas_revision"])
    snap = store.snapshot(channel.name, RUN)
    store.decide(channel.name, RUN, "idea", "no", "отклонён", snap["ideas_revision"])
    brief = (DEMO / "expected" / "briefs" / "01.md").read_text(encoding="utf-8")
    (run / "briefs").mkdir(exist_ok=True)
    (run / "briefs" / "01.md").write_text(brief.replace("- Статус:\n", "- Статус:\n- Идея-ID: good\n"), encoding="utf-8")
    result = call(channel, "check-files", "--step", "idea-briefs")
    assert result.exit_code == 0, result.output
    assert call(channel, "check-files", "--step", "briefs").exit_code == 1  # original strategy count
    (run / "briefs" / "01.md").write_text(brief.replace("- Статус:\n", "- Статус:\n- Идея-ID: no\n"), encoding="utf-8")
    bad = call(channel, "check-files", "--step", "idea-briefs")
    assert bad.exit_code == 1


def test_board_preserves_crlf_while_changing_brief_status(prepared):
    channel, run = prepared
    folder = run / "briefs"
    folder.mkdir(exist_ok=True)
    brief = folder / "01.md"
    brief.write_bytes("# Бриф 1: Идея\r\n- Статус:\r\n## Описание\r\nТекст\r\n".encode())
    store = BoardStore(channel.parent)
    card = store.snapshot(channel.name, RUN)["briefs"][0]
    assert card["status"] == ""
    store.decide(channel.name, RUN, "brief", card["id"], "принят", card["revision"])
    assert brief.read_bytes() == "# Бриф 1: Идея\r\n- Статус: принят\r\n## Описание\r\nТекст\r\n".encode()


def test_agent_targets_explicit_board_run_not_the_latest(prepared):
    channel, original = prepared
    response = call(channel, "start", "--brief-lang", "ru", "--new-version")
    assert response.exit_code == 0, response.output
    payload = {"revision": None, "ideas": [{"id": "first", "title": "Выбор", "source": "report.md", "status": ""}]}
    result = call(channel, "ideas-save", "--run", RUN, input=json.dumps(payload, ensure_ascii=False))
    assert result.exit_code == 0, result.output
    assert (original / "ideas.json").exists()
    assert not (channel / "runs" / "2026-10_ru_v2" / "ideas.json").exists()
    result = call(channel, "ideas-list", "--run", RUN)
    assert result.exit_code == 0 and json.loads(result.output)["ideas"][0]["id"] == "first"


def test_ideas_cannot_be_proposed_before_strategy_approval(prepared):
    channel, run = prepared
    strategy = run / "strategy.md"
    strategy.write_text(strategy.read_text(encoding="utf-8").replace("Статус: утверждена", "Статус: черновик"), encoding="utf-8")
    payload = {"revision": None, "ideas": [{"id": "later", "title": "Тема", "source": "report.md", "status": ""}]}
    result = call(channel, "ideas-save", "--run", RUN, input=json.dumps(payload, ensure_ascii=False))
    assert result.exit_code == 1
    assert not (run / "ideas.json").exists()


@pytest.mark.parametrize("status", ["", "отклонён", "позже"])
def test_unaccepted_ideas_never_generate_briefs(prepared, status):
    channel, run = prepared
    store = BoardStore(channel.parent)
    store.save_ideas(channel.name, RUN,
                     [{"id": "a", "title": "Тема", "source": "report.md", "status": ""}], None)
    if status:
        snap = store.snapshot(channel.name, RUN)
        store.decide(channel.name, RUN, "idea", "a", status, snap["ideas_revision"])
    result = call(channel, "check-files", "--step", "idea-briefs", "--run", RUN)
    assert result.exit_code == 1
    assert not (run / "briefs").exists()


def test_invalid_run_is_not_used_to_write_ideas(prepared):
    channel, run = prepared
    payload = {"revision": None, "ideas": [{"id": "x", "title": "Тема", "source": "report.md", "status": ""}]}
    result = call(channel, "ideas-save", "--run", "../other", input=json.dumps(payload, ensure_ascii=False))
    assert result.exit_code == 1
    assert not (run / "ideas.json").exists()


def test_corrupt_ideas_are_not_replaced(prepared):
    channel, run = prepared
    ideas = run / "ideas.json"
    original = b"{incomplete"
    ideas.write_bytes(original)
    result = call(channel, "ideas-list", "--run", RUN)
    assert result.exit_code == 1
    result = call(channel, "check-files", "--step", "idea-briefs", "--run", RUN)
    assert result.exit_code == 1
    assert ideas.read_bytes() == original


def test_plan_rejects_previously_approved_brief_when_idea_is_rejected(prepared):
    channel, run = prepared
    settings = channel / "settings.yaml"
    settings.write_text(settings.read_text(encoding="utf-8").replace(
        "min_videos_per_month: 2", "min_videos_per_month: 1"), encoding="utf-8")
    store = BoardStore(channel.parent)
    store.save_ideas(channel.name, RUN,
                     [{"id": "good", "title": "Идея", "source": "report.md", "status": ""}], None)
    snap = store.snapshot(channel.name, RUN)
    store.decide(channel.name, RUN, "idea", "good", "принят", snap["ideas_revision"])
    (run / "briefs").mkdir(exist_ok=True)
    brief = (DEMO / "expected" / "briefs" / "01.md").read_text(encoding="utf-8")
    (run / "briefs" / "01.md").write_text(brief.replace("- Статус:\n", "- Статус:\n- Идея-ID: good\n"), encoding="utf-8")
    assert call(channel, "check-files", "--step", "idea-briefs", "--run", RUN).exit_code == 0
    snap = store.snapshot(channel.name, RUN)
    card = snap["briefs"][0]
    store.decide(channel.name, RUN, "brief", card["id"], "принят", card["revision"])
    plan = ("# План месяца\n\n- Запуск: 2026-10, сегмент ru\n- Принятых брифов: 1\n"
            "- Пределы из настроек: 1–12\n\n## Неделя 1\n\n"
            "- Бриф 1 (длинное видео): «Нейросеть для таблиц без формул» — `briefs/01.md`\n")
    (run / "plan.md").write_text(plan, encoding="utf-8")
    assert call(channel, "check-files", "--step", "plan", "--run", RUN).exit_code == 0
    snap = store.snapshot(channel.name, RUN)
    store.decide(channel.name, RUN, "idea", "good", "отклонён", snap["ideas_revision"])
    outcome = call(channel, "check-files", "--step", "plan", "--run", RUN)
    assert outcome.exit_code == 1, outcome.output
    assert "идея" in outcome.output.lower()


def test_explicit_run_status_reads_selected_run_without_starting_new_one(prepared):
    channel, _run = prepared
    result = call(channel, "start", "--brief-lang", "ru", "--new-version")
    assert result.exit_code == 0, result.output
    before = sorted(p.name for p in (channel / "runs").iterdir())
    old = call(channel, "run-status", "--run", RUN)
    assert old.exit_code == 0, old.output
    assert RUN in old.output and "залёты" in old.output
    assert sorted(p.name for p in (channel / "runs").iterdir()) == before
    missing = call(channel, "run-status", "--run", "2026-09_ru_v1")
    assert missing.exit_code == 1
    assert sorted(p.name for p in (channel / "runs").iterdir()) == before


def test_agent_routes_explicit_board_run_before_legacy_start():
    root = DEMO.parent.parent
    text = (root / "playbooks" / "00-month.md").read_text(encoding="utf-8")
    continuation = text.split("## Продолжить месяц", 1)[1]
    assert continuation.index("до команды `start`") < continuation.index("действует прежний порядок")
    assert "run-status --segment <сегмент> --run <имя выбранного запуска>" in continuation
    assert "не переключайтесь на последний запуск" in continuation
    assert "не запускайте её наугад" in continuation
    assert "При отсутствии файла идей и явной просьбы о доске сохраняйте прежний сценарий" in text
    strategy = (root / "playbooks" / "05-strategy.md").read_text(encoding="utf-8")
    assert "при явной просьбе о доске или существующем `ideas.json`" in strategy
