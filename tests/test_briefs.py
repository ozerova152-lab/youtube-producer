"""T11: бриф длинного видео — `check-files --step briefs`.

Сети нет: запуск строится из демо-файла импорта. Смысл брифа скрипт не проверяет.
"""

import json

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json

RUN = "2026-10_ru_v1"
SAMPLE = (DEMO / "expected" / "briefs" / "01.md").read_text(encoding="utf-8")
STRATEGY = (DEMO / "expected" / "strategy.md").read_text(encoding="utf-8")
# T12: число брифов каждого вида сверяется со стратегией; у этих тестов один бриф длинного видео.
STRATEGY = (STRATEGY.replace("Длинные видео в месяц: 4", "Длинные видео в месяц: 1")
            .replace("Shorts в месяц: 2", "Shorts в месяц: 0")
            .replace("Посты в Сообществе в месяц: 4", "Посты в Сообществе в месяц: 0")
            .replace("Роликов в месяц: 6", "Роликов в месяц: 1"))


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
    (path / "strategy.md").write_text(
        STRATEGY.replace("Статус: черновик", "Статус: утверждена"), encoding="utf-8")
    return path


def put(run, text=SAMPLE, name="01.md"):
    (run / "briefs").mkdir(exist_ok=True)
    (run / "briefs" / name).write_text(text, encoding="utf-8")


def check(channel):
    return invoke(channel, "check-files", "--step", "briefs")


def stage(run):
    return read_json(run / "run.json")["stage"]


def test_sample_is_green_and_sets_stage(channel, run):
    put(run)
    res = check(channel)
    assert res.exit_code == 0, res.output
    assert "Бриф 1 из 1: длинное видео «Нейросеть для таблиц без формул»" in res.output
    assert "Проверено брифов: 1, ошибок нет" in res.output
    assert stage(run) == "брифы на решение"


def test_new_brief_has_empty_status():
    assert "\n- Статус:\n" in SAMPLE
    template = (DEMO.parent.parent / "templates" / "brief-long.md").read_text(encoding="utf-8")
    assert "\n- Статус:\n" in template


def test_draft_strategy_blocks_briefs(channel, run):
    (run / "strategy.md").write_text(STRATEGY, encoding="utf-8")
    put(run)
    res = check(channel)
    assert res.exit_code == 1 and "«черновик»" in res.output
    assert stage(run) != "брифы на решение"


def test_no_briefs(channel, run):
    res = check(channel)
    assert res.exit_code == 1 and "брифов нет" in res.output


@pytest.mark.parametrize("field", [
    "Идея", "Залёт", "Чем отличаемся", "Первые 15 секунд", "Длина", "Название 1", "Название 2",
    "Описание триггерное", "Описание SEO", "Хэштеги", "Теги", "Идея обложки", "Эмоции",
])
def test_missing_field_is_named(channel, run, field):
    lines = [x for x in SAMPLE.splitlines() if not x.startswith(f"- {field}:")]
    put(run, "\n".join(lines) + "\n")
    res = check(channel)
    assert res.exit_code == 1
    assert "`briefs/01.md`" in res.output and f"нет поля «{field}»" in res.output
    assert stage(run) != "брифы на решение"


def test_empty_and_placeholder_field(channel, run):
    put(run, SAMPLE.replace("- Длина: 10–12 минут", "- Длина:"))
    assert "поле «Длина» пустое" in check(channel).output
    put(run, SAMPLE.replace("10–12 минут", "<например, 10–12 минут>"))
    assert "поле «Длина» не заполнено" in check(channel).output


def test_structure_needs_edit_marks(channel, run):
    put(run, SAMPLE.replace("[монтаж:", "[заметка:"))
    assert "нет пометок по монтажу" in check(channel).output


def test_samples_must_be_real_virals(channel, run):
    put(run, SAMPLE.replace("- demo_v07:", "- demo_v99:"))
    assert "образец `demo_v99` не залёт" in check(channel).output
    put(run, SAMPLE.replace("watch?v=demo_v07", "watch?v=other"))
    assert "ссылка" in check(channel).output
    put(run, SAMPLE.replace("- Залёт: demo_v01", "- Залёт: demo_v55"))
    assert "залёт `demo_v55` не найден" in check(channel).output


def test_one_sample_is_not_enough(channel, run):
    put(run, "\n".join(x for x in SAMPLE.splitlines() if not x.startswith("- demo_v07")) + "\n")
    assert "нужно 2–3 образца" in check(channel).output


def test_status_must_be_empty_before_decision(channel, run):
    put(run, SAMPLE.replace("- Статус:\n", "- Статус: принят\n"))
    res = check(channel)
    assert res.exit_code == 1 and "Статус ставит человек" in res.output
    put(run, SAMPLE.replace("- Статус:\n", "- Статус: принято!\n"))
    assert "не распознан" in check(channel).output


def test_status_by_human_after_stop_is_accepted(channel, run):
    put(run)
    assert check(channel).exit_code == 0
    put(run, SAMPLE.replace("- Статус:\n", "- Статус: принят\n"))
    assert check(channel).exit_code == 0


def test_brief_language_must_match_run(channel, run):
    put(run, SAMPLE.replace("- Язык брифа: ru", "- Язык брифа: en"))
    assert "а в запуске `--brief-lang` «ru»" in check(channel).output
    # текст на латинице при языке ru
    data = read_json(run / "run.json")
    english = SAMPLE.replace("Нейросеть собрала мне таблицу за 5 минут: без формул",
                             "A neural network built me a spreadsheet in five minutes")
    put(run, english)
    assert "поле «Название 1» не на языке брифа «ru»" in check(channel).output
    # язык en в запуске: русский текст не принимается, сообщения остаются по-русски
    data["brief_lang"] = "en"
    (run / "run.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    put(run, SAMPLE.replace("- Язык брифа: ru", "- Язык брифа: en"))
    res = check(channel)
    assert res.exit_code == 1 and "не на языке брифа «en»" in res.output


def test_english_brief_passes_when_run_is_en(channel, run):
    data = read_json(run / "run.json")
    data["brief_lang"] = "en"
    (run / "run.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    text = SAMPLE.replace("- Язык брифа: ru", "- Язык брифа: en")
    for name, value in {
        "Идея": "Show a beginner how a free neural network builds a working table from a plain request.",
        "Первые 15 секунд": "Here is a monthly expenses table. I wrote no formulas in it.",
        "Название 1": "A neural network built me a table in five minutes",
        "Описание триггерное": "Afraid of formulas? Watch a free neural network build a table for you.",
        "Описание SEO": "How to use a neural network for tables: a step by step example for beginners.",
    }.items():
        text = "\n".join(f"- {name}: {value}" if x.startswith(f"- {name}:") else x
                         for x in text.splitlines()) + "\n"
    put(run, text)
    res = check(channel)
    assert res.exit_code == 0, res.output
    assert "Проверено брифов: 1" in res.output


def test_unknown_kind_and_numbering(channel, run):
    put(run, SAMPLE.replace("- Вид: длинное видео", "- Вид: балет"))
    assert "вид «балет» не распознан" in check(channel).output
    put(run, SAMPLE.replace("# Бриф 1:", "# Бриф 2:"))
    assert "в заголовке номер 2" in check(channel).output


def test_broken_file_is_not_modified(channel, run):
    put(run, "\x00\x01")
    (run / "briefs" / "02.md").write_bytes(b"\xff\xfe\xfa")
    before = (run / "briefs" / "02.md").read_bytes()
    res = check(channel)
    assert res.exit_code == 1 and "Traceback" not in res.output
    assert (run / "briefs" / "02.md").read_bytes() == before


def test_plan_step_still_not_connected(channel, run):
    res = invoke(channel, "check-files", "--step", "plan")
    assert res.exit_code == 1 and "ещё не подключена" in res.output


def test_playbook_exists_and_keeps_places_for_t12_t13():
    text = (DEMO.parent.parent / "playbooks" / "06-briefs-plan.md").read_text(encoding="utf-8")
    for heading in ("Длинное видео", "Shorts и посты", "Статусы и план"):
        assert heading in text, heading
