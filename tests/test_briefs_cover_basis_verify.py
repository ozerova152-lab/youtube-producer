"""T26 (независимая проверка): «Опора обложки» — враждебные случаи, Shorts, посты, later/start.

Сети нет. Критерии берутся из задачи T26 и потока 4 в `docs/spec/04-user-flows.md`.
"""

import re

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core import history, runs

RUN = "2026-10_ru_v1"
EXP = DEMO / "expected"
ROOT = DEMO.parent.parent
LONG, SHORT, POST = ((EXP / "briefs" / f"{n}.md").read_text(encoding="utf-8")
                     for n in ("01", "02", "03"))
COVERS = (EXP / "covers.md").read_text(encoding="utf-8")
COVERS_NONE = (EXP / "covers_no_data.md").read_text(encoding="utf-8")
STRATEGY3 = (EXP / "strategy_three_briefs.md").read_text(encoding="utf-8")
DECIDED = {p.name: p.read_text(encoding="utf-8") for p in sorted((EXP / "briefs_decided").glob("*.md"))}


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def invoke(channel, *args, segment="ru"):
    return CliRunner().invoke(app, ["--channel", str(channel), *args, "--segment", segment])


@pytest.fixture
def run(channel):
    assert invoke(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    assert invoke(channel, "virals").exit_code == 0
    path = channel / "runs" / RUN
    (path / "strategy.md").write_text(
        STRATEGY3.replace("Статус: черновик", "Статус: утверждена"), encoding="utf-8")
    return path


def with_basis(text, basis, anchor="- Идея обложки:"):
    """Вставляет строку опоры сразу после «Идеи обложки»."""
    lines = text.split("\n")
    i = next(k for k, x in enumerate(lines) if x.startswith(anchor))
    lines.insert(i + 1, f"- Опора обложки: {basis}")
    return "\n".join(lines)


def put(run, long=LONG, short=SHORT, post=POST):
    (run / "briefs").mkdir(exist_ok=True)
    for name, text in (("01.md", long), ("02.md", short), ("03.md", post)):
        (run / "briefs" / name).write_text(text, encoding="utf-8")


def check(channel):
    return invoke(channel, "check-files", "--step", "briefs")


def test_all_three_kinds_with_valid_basis_green(channel, run):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    put(run, with_basis(LONG, "demo_v01"), with_basis(SHORT, "demo_v07"), POST)
    res = check(channel)
    assert res.exit_code == 0, res.output


@pytest.mark.parametrize("bad", [
    "DEMO_V01", "demo_v01 demo_v07", "demo_v01, demo_v07", "../x", "../../covers.md",
    "2026-09_ru_v1/demo_v01", "demo_v99", "demo_v", "<id>", "<id залёта из covers.md>",
])
def test_bad_basis_red_names_file_and_id_long_and_short(channel, run, bad):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    for which in ("01.md", "02.md"):
        text = with_basis(LONG if which == "01.md" else SHORT, bad)
        put(run, long=text if which == "01.md" else LONG,
            short=text if which == "02.md" else SHORT)
        res = check(channel)
        assert res.exit_code == 1, (bad, res.output)
        assert f"`briefs/{which}`" in res.output
        if "<" not in bad:
            assert bad.strip() in res.output


@pytest.mark.parametrize("raw", ["", "   ", "\t"])
def test_empty_basis_value_is_red_or_ignored_never_crash(channel, run, raw):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    put(run, with_basis(LONG, raw))
    res = check(channel)
    assert res.exception is None or isinstance(res.exception, SystemExit), res.output
    assert "Traceback" not in res.output


def test_id_in_idea_but_not_in_basis_is_red(channel, run):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    idea = next(x for x in LONG.splitlines() if x.startswith("- Идея обложки:"))
    text = LONG.replace(idea, idea + " (см. demo_v01)")
    text = with_basis(text, "ghost_1")
    put(run, text)
    res = check(channel)
    assert res.exit_code == 1 and "`ghost_1`" in res.output


def test_basis_from_other_run_id_red(channel, run):
    # id залёта, которого нет в covers.md этого запуска (например, из прошлого месяца).
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    put(run, with_basis(LONG, "old_run_v05"))
    res = check(channel)
    assert res.exit_code == 1 and "`old_run_v05`" in res.output and "`briefs/01.md`" in res.output


@pytest.mark.parametrize("basis", ["demo_v01", "anything", "<tpl>"])
def test_covers_none_mode_any_basis_red(channel, run, basis):
    (run / "covers.md").write_text(COVERS_NONE, encoding="utf-8")
    put(run, with_basis(LONG, basis))
    assert check(channel).exit_code == 1


def test_no_covers_no_basis_green_and_with_basis_green(channel, run):
    put(run)
    assert check(channel).exit_code == 0
    put(run, with_basis(LONG, "x"), with_basis(SHORT, "y"))
    assert check(channel).exit_code == 0


def test_post_with_basis_line_does_not_break(channel, run):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    put(run, post=with_basis(POST, "demo_v01", anchor="- Формат:"))
    res = check(channel)
    assert res.exit_code == 0, res.output
    put(run, post=with_basis(POST, "ghost", anchor="- Формат:"))
    res = check(channel)
    # у постов нет «Идеи обложки»: опора в посте не проверяется и ложной ошибки не даёт
    assert res.exit_code == 0, res.output


@pytest.mark.parametrize("idea", ["", "   ", "<что на картинке и какая надпись>"])
def test_idea_cover_empty_or_template_red_with_covers_and_basis(channel, run, idea):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    old = next(x for x in LONG.splitlines() if x.startswith("- Идея обложки:"))
    put(run, with_basis(LONG.replace(old, f"- Идея обложки: {idea}"), "demo_v01"))
    res = check(channel)
    assert res.exit_code == 1 and "Идея обложки" in res.output


def test_idea_cover_empty_red_without_covers(channel, run):
    old = next(x for x in LONG.splitlines() if x.startswith("- Идея обложки:"))
    put(run, LONG.replace(old, "- Идея обложки:"))
    res = check(channel)
    assert res.exit_code == 1 and "Идея обложки" in res.output


def test_later_copies_basis_verbatim_and_new_run_checks_it(channel, run):
    old = channel / "runs" / "2026-09_ru_v1"
    (old / "briefs").mkdir(parents=True)
    (old / "run.json").write_text(
        '{"month": "2026-09", "segment": "ru", "brief_lang": "ru", "version": 1, '
        '"stage": "план готов", "quota_spent": 0, "requests_count": 0, '
        '"awaiting_confirmation": false, "incomplete_data": []}', encoding="utf-8")
    with_op = with_basis(re.sub(r"^- Статус:.*$", "- Статус: позже", DECIDED["01.md"],
                                count=1, flags=re.MULTILINE), "oldvid_77")
    without = re.sub(r"^- Статус:.*$", "- Статус: позже", DECIDED["02.md"], count=1,
                     flags=re.MULTILINE)
    (old / "briefs" / "01.md").write_text(with_op, encoding="utf-8")
    (old / "briefs" / "02.md").write_text(without, encoding="utf-8")
    before = {p.name: p.read_bytes() for p in (old / "briefs").glob("*.md")}
    res = invoke(channel, "later", "--all")
    assert res.exit_code == 0, res.output
    assert {p.name: p.read_bytes() for p in (old / "briefs").glob("*.md")} == before
    copies = sorted((run / "briefs").glob("*.md"))
    texts = [c.read_text(encoding="utf-8") for c in copies]
    assert any("- Опора обложки: oldvid_77" in t for t in texts)
    assert sum("Опора обложки" in t for t in texts) == 1
    # без covers.md в новом запуске опора молчит
    cur = runs.list_runs(channel, "2026-10", "ru")[0]
    assert history.past_briefs(channel, "ru", cur)
    r = check(channel)
    assert "Опора обложки" not in r.output
    # а с covers.md нового запуска id из прошлого — красная, как задумано (id не из этого covers.md)
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    r = check(channel)
    assert "`oldvid_77`" in r.output


def test_templates_playbook_and_spec_texts():
    for name in ("brief-long.md", "brief-short.md"):
        text = (ROOT / "templates" / name).read_text(encoding="utf-8")
        line = next(x for x in text.splitlines() if x.startswith("- Опора обложки:"))
        assert "только если есть covers.md" in line and "необязательно" in line
        idea = next(x for x in text.splitlines() if x.startswith("- Идея обложки:"))
        assert "<" in idea  # остаётся обязательным шаблонным полем
    post = (ROOT / "templates" / "brief-post.md").read_text(encoding="utf-8")
    assert "Опора обложки" not in post
    spec = (ROOT / "docs" / "spec" / "04-user-flows.md").read_text(encoding="utf-8")
    assert "не найдена среди залётов `covers.md`. Укажите id из `covers.md` или удалите строку" in spec
