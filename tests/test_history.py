"""T14: история запусков — повторы тем в `check-files`, `produce later`, версии и сегменты.

Сети нет. Прошлые запуски строятся в копии демо-канала из образцов брифов
`examples/demo/expected/briefs_decided/`: меняются названия и статусы, как это делает человек.
"""

import hashlib
import json
import re

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app

RUN = "2026-10_ru_v1"
EXP = DEMO / "expected"
DECIDED = {p.name: p.read_text(encoding="utf-8") for p in sorted((EXP / "briefs_decided").glob("*.md"))}
STRATEGY = (EXP / "strategy_three_briefs.md").read_text(encoding="utf-8")
OLD_TITLE = "Нейросеть для презентаций без дизайнера"


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def invoke(channel, *args, segment="ru"):
    return CliRunner().invoke(app, ["--channel", str(channel), *args, "--segment", segment])


def with_status(text, value):
    return re.sub(r"^- Статус:.*$", f"- Статус: {value}".rstrip(), text, count=1, flags=re.MULTILINE)


def with_title(text, title):
    return re.sub(r"^# Бриф (\d+): .*$", rf"# Бриф \1: {title}", text, count=1, flags=re.MULTILINE)


def make_run(channel, name, stage="план готов", briefs=None):
    """Прошлый запуск: папка, `run.json` и брифы вида {номер: (название, статус, исходный файл)}."""
    month, segment, version = re.match(r"(\d{4}-\d{2})_(.+)_v(\d+)$", name).groups()
    path = channel / "runs" / name
    (path / "briefs").mkdir(parents=True)
    (path / "run.json").write_text(json.dumps({
        "month": month, "segment": segment, "brief_lang": "ru", "version": int(version),
        "stage": stage, "quota_spent": 0, "requests_count": 0, "awaiting_confirmation": False,
        "incomplete_data": []}, ensure_ascii=False), encoding="utf-8")
    for number, (title, status, source) in (briefs or {}).items():
        text = with_status(with_title(DECIDED[source], title), status)
        (path / "briefs" / f"{number:02d}.md").write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def run(channel):
    """Текущий запуск 2026-10 на этапе «стратегия утверждена» с демо-залётами."""
    assert invoke(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    assert invoke(channel, "virals").exit_code == 0
    path = channel / "runs" / RUN
    (path / "strategy.md").write_text(
        STRATEGY.replace("Статус: черновик", "Статус: утверждена"), encoding="utf-8")
    assert invoke(channel, "check-files", "--step", "strategy").exit_code == 0
    return path


def write_current(run, names=("01.md", "02.md", "03.md")):
    (run / "briefs").mkdir(exist_ok=True)
    for name in names:
        (run / "briefs" / name).write_text(with_status(DECIDED[name], ""), encoding="utf-8")


def test_rejected_topic_in_other_words_is_found_in_briefs(channel, run):
    make_run(channel, "2026-09_ru_v1", briefs={4: (OLD_TITLE, "отклонён", "04.md")})
    write_current(run)
    # Те же слова в другом порядке и другой форме: «презентации» -> «презентаций».
    (run / "briefs" / "01.md").write_text(with_status(
        with_title(DECIDED["01.md"], "Как нейросети делают презентации без дизайнера"), ""),
        encoding="utf-8")
    res = invoke(channel, "check-files", "--step", "briefs")
    assert res.exit_code == 1
    assert (f"Тема «{OLD_TITLE}» отклонена в 2026-09 "
            "(бриф `2026-09_ru_v1/briefs/04.md`). Замените её") in res.output
    assert "briefs/01.md" in res.output
    assert json.loads((run / "run.json").read_text())["stage"] == "стратегия утверждена"


def test_same_source_video_of_rejected_brief_is_found(channel, run):
    # Слов общих мало (одно), но залёт-основа та же, что у отклонённого брифа.
    make_run(channel, "2026-09_ru_v1", briefs={4: ("Три ошибки новичка в первом запросе", "отклонён", "04.md")})
    write_current(run)
    (run / "briefs" / "01.md").write_text(
        with_status(with_title(DECIDED["01.md"], "Ошибки начинающих"), ""), encoding="utf-8")
    res = invoke(channel, "check-files", "--step", "briefs")
    assert res.exit_code == 1 and "«Три ошибки новичка в первом запросе» отклонена в 2026-09" in res.output
    assert "`briefs/01.md`" in res.output


def test_same_source_alone_or_niche_word_is_not_a_repeat(channel, run):
    # Все демо-брифы на одном залёте и все про нейросети: этого мало для повтора.
    make_run(channel, "2026-09_ru_v1", briefs={4: ("Три ошибки новичка в первом запросе к нейросети",
                                                   "отклонён", "04.md")})
    write_current(run)
    assert invoke(channel, "check-files", "--step", "briefs").exit_code == 0


def test_briefs_pass_without_history_and_with_unrelated_history(channel, run):
    write_current(run)
    assert invoke(channel, "check-files", "--step", "briefs").exit_code == 0
    assert json.loads((run / "run.json").read_text())["stage"] == "брифы на решение"


def test_unrelated_rejected_topic_is_not_a_repeat(channel, run):
    path = make_run(channel, "2026-09_ru_v1", briefs={4: ("Обзор микрофонов для подкаста", "отклонён", "04.md")})
    # Основа другого залёта: в этом прошлом запуске она не совпадает с основой новых брифов.
    f = path / "briefs" / "04.md"
    f.write_text(f.read_text(encoding="utf-8").replace("- Залёт: demo_v01", "- Залёт: demo_v99"),
                 encoding="utf-8")
    write_current(run)
    assert invoke(channel, "check-files", "--step", "briefs").exit_code == 0


def test_proposed_topic_is_found_with_status(channel, run):
    make_run(channel, "2026-09_ru_v1", briefs={1: ("Нейросеть для таблиц без формул", "принят", "01.md")})
    write_current(run)
    res = invoke(channel, "check-files", "--step", "briefs")
    assert res.exit_code == 1
    assert "уже предлагалась в 2026-09" in res.output and "статус «принят»" in res.output


def test_strategy_repeat_is_found_and_stage_not_advanced(channel, run):
    make_run(channel, "2026-09_ru_v1", briefs={4: (OLD_TITLE, "отклонён", "04.md")})
    (run / "strategy.md").write_text(
        STRATEGY.replace("- Почему такой баланс: ", "- Почему такой баланс: берём тему презентаций без дизайнера с нейросетью; "),
        encoding="utf-8")
    res = invoke(channel, "check-files", "--step", "strategy")
    assert res.exit_code == 1
    assert f"Тема «{OLD_TITLE}» отклонена в 2026-09" in res.output and "`strategy.md`" in res.output
    assert json.loads((run / "run.json").read_text())["stage"] != "стратегия ждёт утверждения"


def test_strategy_without_repeat_passes_with_history(channel):
    assert invoke(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    make_run(channel, "2026-09_ru_v1", briefs={4: (OLD_TITLE, "отклонён", "04.md")})
    (channel / "runs" / RUN / "strategy.md").write_text(STRATEGY, encoding="utf-8")
    assert invoke(channel, "virals").exit_code == 0
    assert invoke(channel, "check-files", "--step", "strategy").exit_code == 0


def test_v1_and_v2_of_one_month_both_count(channel, run):
    make_run(channel, "2026-09_ru_v1", briefs={4: ("Три ошибки новичка в запросе", "отклонён", "04.md")})
    make_run(channel, "2026-09_ru_v2", briefs={4: (OLD_TITLE, "отклонён", "04.md")})
    for text in ("Три ошибки новичка в запросе к нейросети", OLD_TITLE):
        write_current(run)
        (run / "briefs" / "01.md").write_text(
            with_status(with_title(DECIDED["01.md"], text), ""), encoding="utf-8")
        res = invoke(channel, "check-files", "--step", "briefs")
        assert res.exit_code == 1 and "отклонена в 2026-09" in res.output, text
    assert "2026-09_ru_v1/briefs/04.md" in res.output or "2026-09_ru_v2/briefs/04.md" in res.output


def test_v2_checks_against_v1_of_same_month_and_ignores_newer(channel):
    assert invoke(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    v1 = channel / "runs" / RUN
    (v1 / "briefs").mkdir()
    (v1 / "briefs" / "01.md").write_text(
        with_status(with_title(DECIDED["01.md"], OLD_TITLE), "отклонён"), encoding="utf-8")
    make_run(channel, "2026-11_ru_v1", briefs={4: ("Совсем новое про микрофоны", "отклонён", "04.md")})
    from produce.core import history, runs
    run = runs.list_runs(channel, "2026-10", "ru")[0]
    # Текущий запуск себя не считает, более новый месяц в историю не входит.
    assert history.past_briefs(channel, "ru", run) == []
    runs.set_stage(run, "план готов")
    v2 = runs.start_run(channel, "2026-10", "ru", "ru").run
    assert v2.path.name == "2026-10_ru_v2"
    assert [b.title for b in history.past_briefs(channel, "ru", v2)] == [OLD_TITLE]


def test_segments_do_not_mix(channel, run):
    make_run(channel, "2026-09_en_v1", briefs={4: (OLD_TITLE, "отклонён", "04.md"),
                                               5: ("One question for AI", "позже", "05.md")})
    write_current(run)
    (run / "briefs" / "01.md").write_text(
        with_status(with_title(DECIDED["01.md"], OLD_TITLE), ""), encoding="utf-8")
    assert invoke(channel, "check-files", "--step", "briefs").exit_code == 0
    res = invoke(channel, "later")
    assert res.exit_code == 0 and "Прошлых запусков нет" in res.output
    assert "One question" not in res.output
    res = invoke(channel, "later", "--all")
    assert res.exit_code == 0 and "Прошлых запусков нет" in res.output
    assert not list((run / "briefs").glob("04.md"))
    # в самом en история есть
    en = invoke(channel, "later", segment="en")
    assert "One question for AI" in en.output


def test_later_without_history(channel):
    res = invoke(channel, "later")
    assert res.exit_code == 0 and res.output.strip() == "Прошлых запусков нет"


def test_later_lists_and_returns_picked(channel, run):
    old = make_run(channel, "2026-09_ru_v1", briefs={
        3: ("Один вопрос нейросети", "позже", "05.md"),
        4: (OLD_TITLE, "отклонён", "04.md"),
        5: ("Письмо за 40 секунд", "позже", "02.md"),
        6: ("Таблицы без формул", "принят", "01.md")})
    before = {p.name: p.read_bytes() for p in (old / "briefs").glob("*.md")}
    write_current(run)
    listing = invoke(channel, "later")
    assert listing.exit_code == 0
    assert "Отклонено в прошлых запусках: 1 тема. Брифов «позже»: 2. Вернуть?" in listing.output
    assert f"«{OLD_TITLE}»" in listing.output and "1. «Один вопрос нейросети»" in listing.output
    assert "2. «Письмо за 40 секунд»" in listing.output
    assert len(list((run / "briefs").glob("*.md"))) == 3  # листинг ничего не копирует

    res = invoke(channel, "later", "--pick", "1", "--pick", "2")
    assert res.exit_code == 0, res.output
    assert "Возвращено брифов: 2" in res.output
    copied = (run / "briefs" / "04.md").read_text(encoding="utf-8")
    assert "# Бриф 4: Один вопрос нейросети" in copied
    assert re.search(r"^- Статус:\s*$", copied, re.MULTILINE)  # решать заново
    assert "- Возвращён из: 2026-09_ru_v1, бриф 03" in copied
    assert "- Запуск: 2026-10, сегмент ru" in copied
    assert (run / "briefs" / "05.md").is_file() and not (run / "briefs" / "06.md").exists()
    # старый запуск не изменился
    assert {p.name: p.read_bytes() for p in (old / "briefs").glob("*.md")} == before
    # Возвращённые больше не предлагаются
    again = invoke(channel, "later")
    assert "Брифов «позже»: 0" in again.output and "Брифов «позже» нет" in again.output


def test_returned_copy_is_not_a_repeat_of_its_source(channel, run):
    make_run(channel, "2026-09_ru_v1", briefs={3: ("Нейросеть для таблиц без формул", "позже", "01.md")})
    write_current(run, ("02.md", "03.md"))
    # возвращённый бриф идёт номером 03 и не тормозится собственным источником
    assert invoke(channel, "later", "--pick", "1").exit_code == 0
    new = [p for p in (run / "briefs").glob("*.md") if "Возвращён из" in p.read_text(encoding="utf-8")]
    assert len(new) == 1
    from produce.core import history, runs
    cur = runs.list_runs(channel, "2026-10", "ru")[0]
    assert history.brief_repeats(channel, cur) == []


def test_later_bad_number_and_no_run(channel, run):
    make_run(channel, "2026-09_ru_v1", briefs={3: ("Один вопрос", "позже", "05.md")})
    res = invoke(channel, "later", "--pick", "7")
    assert res.exit_code == 1 and "Нет брифа «позже» под номером 7" in res.output


def test_later_without_current_run_refuses_copy(channel):
    make_run(channel, "2026-09_ru_v1", briefs={3: ("Один вопрос", "позже", "05.md")})
    assert "Брифов «позже»: 1" in invoke(channel, "later").output
    res = invoke(channel, "later", "--all")
    assert res.exit_code == 1 and "сначала `produce start`" in res.output


def test_rejected_is_never_returned_by_script(channel, run):
    old = make_run(channel, "2026-09_ru_v1", briefs={4: (OLD_TITLE, "отклонён", "04.md")})
    res = invoke(channel, "later", "--all")
    assert res.exit_code == 1 and "Брифов «позже» нет" in res.output
    assert "отклонён" in (old / "briefs" / "04.md").read_text(encoding="utf-8")
    # человек возвращает вручную: меняет статус в старом брифе
    f = old / "briefs" / "04.md"
    f.write_text(with_status(f.read_text(encoding="utf-8"), "позже"), encoding="utf-8")
    assert "Брифов «позже»: 1" in invoke(channel, "later").output


def test_settings_untouched(channel, run):
    digest = hashlib.sha256((channel / "settings.yaml").read_bytes()).hexdigest()
    make_run(channel, "2026-09_ru_v1", briefs={3: ("Один вопрос", "позже", "05.md")})
    write_current(run)
    invoke(channel, "later", "--all")
    invoke(channel, "check-files", "--step", "briefs")
    assert hashlib.sha256((channel / "settings.yaml").read_bytes()).hexdigest() == digest


def test_twelve_runs_resume_unfinished_instead_of_v2(channel):
    # 6 месяцев по два сегмента; в 2026-10 ru есть v1 (готов) и v2 (остановлен на стратегии)
    for month in ("2026-05", "2026-06", "2026-07", "2026-08", "2026-09"):
        make_run(channel, f"{month}_ru_v1")
        make_run(channel, f"{month}_en_v1")
    make_run(channel, "2026-10_en_v1", stage="собрано")
    make_run(channel, "2026-10_ru_v1")
    make_run(channel, "2026-10_ru_v2", stage="стратегия ждёт утверждения")
    assert len(list((channel / "runs").iterdir())) == 13
    (channel / "runs" / "2026-10_ru_v1" / "briefs").rmdir()
    res = invoke(channel, "start", "--brief-lang", "ru")
    assert res.exit_code == 0, res.output
    assert "Запуск 2026-10, ru, v2. Этап: стратегия ждёт утверждения. Продолжить?" in res.output
    assert not (channel / "runs" / "2026-10_ru_v3").exists()


def test_twelve_runs_new_v2_only_after_plan_ready(channel):
    for month in ("2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"):
        make_run(channel, f"{month}_ru_v1")
        make_run(channel, f"{month}_en_v1")
    make_run(channel, "2026-10_ru_v1")
    res = invoke(channel, "start", "--brief-lang", "ru")
    assert res.exit_code == 0, res.output
    assert "В этом месяце уже есть v1: создам новую версию" in res.output
    assert (channel / "runs" / "2026-10_ru_v2").is_dir()
    assert "Прошлых запусков нет" not in res.output and "Брифов «позже»: 0" in res.output
    # v1 цела
    assert json.loads((channel / "runs" / "2026-10_ru_v1" / "run.json").read_text())["stage"] == "план готов"


def test_start_first_run_says_no_history(channel):
    res = invoke(channel, "start", "--brief-lang", "ru")
    assert res.exit_code == 0 and "Прошлых запусков нет" in res.output
