"""T13: статусы брифов и месячный план — `check-files --step plan`.

Сети нет: запуск строится из демо-файла импорта. Образцы брифов с разными статусами лежат
в `examples/demo/expected/briefs_decided/`, образец плана — `expected/plan.md`.
"""

import re

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json

RUN = "2026-10_ru_v1"
EXP = DEMO / "expected"
DECIDED = {p.name: p.read_text(encoding="utf-8") for p in sorted((EXP / "briefs_decided").glob("*.md"))}
PLAN = (EXP / "plan.md").read_text(encoding="utf-8")
STRATEGY = (EXP / "strategy_three_briefs.md").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def invoke(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args, "--segment", "ru"])


def stage(run):
    return read_json(run / "run.json")["stage"]


def status_of(text, value):
    return re.sub(r"^- Статус:.*$", f"- Статус: {value}".rstrip(), text, count=1, flags=re.MULTILINE)


@pytest.fixture
def run(channel):
    """Запуск на этапе «брифы на решение»: три брифа 01–03 без статусов (как их пишет агент)."""
    assert invoke(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    assert invoke(channel, "virals").exit_code == 0
    path = channel / "runs" / RUN
    (path / "strategy.md").write_text(
        STRATEGY.replace("Статус: черновик", "Статус: утверждена"), encoding="utf-8")
    (path / "briefs").mkdir()
    for name in ("01.md", "02.md", "03.md"):
        (path / "briefs" / name).write_text(status_of(DECIDED[name], ""), encoding="utf-8")
    res = invoke(channel, "check-files", "--step", "briefs")
    assert res.exit_code == 0, res.output
    return path


def decide(run, **statuses):
    """decide(run, **{"01": "принят"}): правит строку статуса, как это сделал бы человек."""
    for number, value in statuses.items():
        f = run / "briefs" / f"{number}.md"
        f.write_text(status_of(f.read_text(encoding="utf-8"), value), encoding="utf-8")


def add(run, name):
    (run / "briefs" / name).write_text(DECIDED[name], encoding="utf-8")


def plan_check(channel):
    return invoke(channel, "check-files", "--step", "plan")


def test_refused_while_strategy_is_draft(channel, run):
    (run / "strategy.md").write_text(STRATEGY, encoding="utf-8")
    res = plan_check(channel)
    assert res.exit_code == 1 and "«черновик»" in res.output
    assert stage(run) == "брифы на решение"


def test_empty_statuses_are_named(channel, run):
    decide(run, **{"01": "принят", "03": "принят"})
    res = plan_check(channel)
    assert res.exit_code == 1
    assert res.output.strip() == "Нет статуса: 2"


def test_two_empty_of_five_are_named(channel, run):
    add(run, "04.md")
    add(run, "05.md")
    decide(run, **{"01": "принят", "03": "принят", "04": "отклонён"})
    decide(run, **{"02": "", "05": ""})
    res = plan_check(channel)
    assert res.output.strip() == "Нет статуса: 2, 5"
    assert not (run / "plan.md").exists()


def test_shortage_is_named_and_plan_not_filled(channel, run):
    # Предел демо: минимум 2. Принят один.
    decide(run, **{"01": "принят", "02": "позже", "03": "отклонён"})
    res = plan_check(channel)
    assert res.exit_code == 1
    assert res.output.strip() == (
        "Принятых 1, минимум 2. Нехватка: 1. План не добит. Могу сделать ещё брифы или вы смените "
        "статус «позже» на «принят»")
    assert not (run / "plan.md").exists()


def test_excess_is_named_and_nothing_cut(channel, run):
    limits = (channel / "settings.yaml").read_text(encoding="utf-8")
    (channel / "settings.yaml").write_text(
        limits.replace("max_videos_per_month: 12", "max_videos_per_month: 2"), encoding="utf-8")
    decide(run, **{"01": "принят", "02": "принят", "03": "принят"})
    before = {p.name: p.read_bytes() for p in (run / "briefs").glob("*.md")}
    res = plan_check(channel)
    assert res.exit_code == 1
    assert res.output.strip() == ("Принятых 3, максимум 2. Перенесите лишние в «позже» "
                                  "и напишите «готово»")
    assert {p.name: p.read_bytes() for p in (run / "briefs").glob("*.md")} == before


def test_statuses_ok_but_no_plan_yet(channel, run):
    decide(run, **{"01": "принят", "02": "принят", "03": "позже"})
    res = plan_check(channel)
    assert res.exit_code == 1 and "`plan.md`: файла нет" in res.output
    assert stage(run) == "брифы на решение"


def full_set(run):
    add(run, "04.md")
    add(run, "05.md")
    for name in ("01.md", "02.md", "03.md"):
        (run / "briefs" / name).write_text(DECIDED[name], encoding="utf-8")
    (run / "plan.md").write_text(PLAN, encoding="utf-8")


def test_green_plan_sets_stage_and_rejected_do_not_break(channel, run):
    # 5 файлов, а в strategy.md 3 брифа: на шаге плана «ровно» не применяется.
    full_set(run)
    res = plan_check(channel)
    assert res.exit_code == 0, res.output
    assert "Проверено: план из 3 принятых брифов, пределы 2–12, ошибок нет" in res.output
    assert "Месяц готов. Публикацию делаете вы" in res.output
    assert stage(run) == "план готов"
    assert (run / "briefs" / "04.md").exists() and (run / "briefs" / "05.md").exists()


def test_shape_of_demo_plan_has_only_accepted():
    for rejected in ("Бриф 4", "Бриф 5", "04.md", "05.md"):
        assert rejected not in PLAN


def test_rejected_brief_in_plan_is_red(channel, run):
    full_set(run)
    (run / "plan.md").write_text(
        PLAN + "- Бриф 4 (длинное видео): «Три ошибки новичка в первом запросе к нейросети» "
        "— `briefs/04.md`\n", encoding="utf-8")
    res = plan_check(channel)
    assert res.exit_code == 1 and "бриф 4 в плане, а его статус «отклонён»" in res.output
    assert stage(run) == "брифы на решение"


def test_later_brief_in_plan_is_red(channel, run):
    full_set(run)
    (run / "plan.md").write_text(
        PLAN + "- Бриф 5 (Shorts): «Один вопрос нейросети, который экономит час» "
        "— `briefs/05.md`\n", encoding="utf-8")
    res = plan_check(channel)
    assert res.exit_code == 1 and "бриф 5 в плане, а его статус «позже»" in res.output


def test_accepted_brief_missing_and_duplicated(channel, run):
    full_set(run)
    (run / "plan.md").write_text(PLAN.replace(
        "- Бриф 2 (Shorts): «Письмо начальнику за 40 секунд» — `briefs/02.md`\n", ""),
        encoding="utf-8")
    assert "в плане нет принятых брифов: 2" in plan_check(channel).output
    (run / "plan.md").write_text(PLAN + "- Бриф 1 (длинное видео): «Нейросеть для таблиц без формул» "
                                 "— `briefs/01.md`\n", encoding="utf-8")
    assert "бриф 1 записан в плане 2 раза" in plan_check(channel).output


def test_plan_template_is_not_green(channel, run):
    full_set(run)
    (run / "plan.md").write_text((DEMO.parent.parent / "templates" / "plan.md").read_text(
        encoding="utf-8"), encoding="utf-8")
    res = plan_check(channel)
    assert res.exit_code == 1 and "не заполнено" in res.output


@pytest.mark.parametrize("bad", ["Принят", "принято", "accepted", "принят!", "принят принят"])
def test_bad_status_line_names_file_and_place_and_file_untouched(channel, run, bad):
    decide(run, **{"01": "принят", "02": "принят", "03": bad})
    path = run / "briefs" / "03.md"
    before = path.read_bytes()
    for step in ("plan", "briefs"):
        res = invoke(channel, "check-files", "--step", step)
        assert res.exit_code == 1
        assert "`briefs/03.md`, шапка: статус" in res.output and "не распознан" in res.output
    assert path.read_bytes() == before


def test_agent_playbook_does_not_set_statuses_and_stage_only_by_script(channel):
    text = (DEMO.parent.parent / "playbooks" / "06-briefs-plan.md").read_text(encoding="utf-8")
    assert "Нет статуса: 2, 5" in text and "Принятых 9, максимум 8" in text
    assert "Агент статусы не ставит" in text


def test_settings_unchanged(channel, run):
    before = (channel / "settings.yaml").read_bytes()
    full_set(run)
    plan_check(channel)
    assert (channel / "settings.yaml").read_bytes() == before
