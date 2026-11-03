"""T26: необязательная «Опора обложки» в упаковке брифа и её проверка по `covers.md`.

Сети нет: запуск строится из демо-файла импорта. Смысл идеи скрипт не проверяет, только
наличие id среди залётов, разобранных в `covers.md`.
"""

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core import history
from produce.core.files import read_json

RUN = "2026-10_ru_v1"
SAMPLE = (DEMO / "expected" / "briefs" / "01.md").read_text(encoding="utf-8")
COVERS = (DEMO / "expected" / "covers.md").read_text(encoding="utf-8")
IDEA = next(x for x in SAMPLE.splitlines() if x.startswith("- Идея обложки:"))
STRATEGY = ((DEMO / "expected" / "strategy.md").read_text(encoding="utf-8")
            .replace("Длинные видео в месяц: 4", "Длинные видео в месяц: 1")
            .replace("Shorts в месяц: 2", "Shorts в месяц: 0")
            .replace("Посты в Сообществе в месяц: 4", "Посты в Сообществе в месяц: 0")
            .replace("Роликов в месяц: 6", "Роликов в месяц: 1")
            .replace("Статус: черновик", "Статус: утверждена"))


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
    path = channel / "runs" / RUN
    (path / "strategy.md").write_text(STRATEGY, encoding="utf-8")
    return path


def put(run, basis: str | None, name="01.md"):
    text = SAMPLE if basis is None else SAMPLE.replace(IDEA, f"{IDEA}\n- Опора обложки: {basis}")
    (run / "briefs").mkdir(exist_ok=True)
    (run / "briefs" / name).write_text(text, encoding="utf-8")


def check(channel):
    return invoke(channel, "check-files", "--step", "briefs")


def test_valid_basis_is_green(channel, run):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    put(run, "demo_v01")
    res = check(channel)
    assert res.exit_code == 0, res.output
    assert "Проверено брифов: 1, ошибок нет" in res.output


def test_unknown_basis_names_file_and_id(channel, run):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    put(run, "nope_999")
    res = check(channel)
    assert res.exit_code == 1
    assert "`briefs/01.md`" in res.output and "`nope_999`" in res.output
    assert "не найдена среди залётов `covers.md`" in res.output
    assert read_json(run / "run.json")["stage"] != "брифы на решение"


def test_basis_with_covers_none_mode_is_red(channel, run):
    # Разбор пропущен («нет данных»): блоков залётов нет, значит любая опора неверна.
    (run / "covers.md").write_text(
        (DEMO / "expected" / "covers_no_data.md").read_text(encoding="utf-8"), encoding="utf-8")
    put(run, "demo_v01")
    res = check(channel)
    assert res.exit_code == 1 and "`demo_v01`" in res.output


def test_placeholder_basis_is_red(channel, run):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    put(run, "<id залёта из covers.md>")
    res = check(channel)
    assert res.exit_code == 1
    assert "поле «Опора обложки» не заполнено" in res.output


def test_no_covers_file_basis_not_required_and_not_checked(channel, run):
    assert not (run / "covers.md").exists()
    put(run, None)
    assert check(channel).exit_code == 0
    put(run, "anything")  # нет covers.md: сверять не с чем, проверка молчит
    assert check(channel).exit_code == 0


def test_covers_without_basis_line_stays_green(channel, run):
    # Старые брифы в запуске, где covers.md появился позже, не краснеют.
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    put(run, None)
    assert check(channel).exit_code == 0


def test_idea_cover_stays_required(channel, run):
    (run / "covers.md").write_text(COVERS, encoding="utf-8")
    text = SAMPLE.replace(IDEA, "- Опора обложки: demo_v01")
    (run / "briefs").mkdir()
    (run / "briefs" / "01.md").write_text(text, encoding="utf-8")
    res = check(channel)
    assert res.exit_code == 1 and "нет поля «Идея обложки»" in res.output


def test_history_reads_brief_with_basis_like_without(channel, run):
    put(run, None, "01.md")
    plain = history._read_brief(RUN, "2026-10", run / "briefs" / "01.md")
    put(run, "demo_v01", "01.md")
    with_basis = history._read_brief(RUN, "2026-10", run / "briefs" / "01.md")
    assert plain == with_basis and with_basis.status == ""


def test_templates_and_playbook_describe_basis():
    root = DEMO.parent.parent
    for name in ("brief-long.md", "brief-short.md"):
        text = (root / "templates" / name).read_text(encoding="utf-8")
        line = next(x for x in text.splitlines() if x.startswith("- Опора обложки:"))
        assert "необязательно" in line and "только если есть covers.md" in line
        assert "- Идея обложки:" in text
    playbook = (root / "playbooks" / "06-briefs-plan.md").read_text(encoding="utf-8")
    assert "а не придумывается" in playbook and "дословно не копируй" in playbook
