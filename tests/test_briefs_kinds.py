"""T12: брифы Shorts и поста в Сообщество — `check-files --step briefs`.

Сети нет: запуск строится из демо-файла импорта. Смысл брифа скрипт не проверяет.
Стратегия берётся из `strategy_three_briefs.md`: по одному брифу каждого вида.
"""

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json

RUN = "2026-10_ru_v1"
ROOT = DEMO.parent.parent
LONG, SHORT, POST = ((DEMO / "expected" / "briefs" / f"{n}.md").read_text(encoding="utf-8")
                     for n in ("01", "02", "03"))
STRATEGY = (DEMO / "expected" / "strategy_three_briefs.md").read_text(encoding="utf-8")
POST_TEXT = POST.split("## Готовый текст\n")[1].split("## Опрос")[0]


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


def put(run, long=LONG, short=SHORT, post=POST):
    """Записывает три брифа 01–03; None — файла нет."""
    (run / "briefs").mkdir(exist_ok=True)
    for name, text in (("01.md", long), ("02.md", short), ("03.md", post)):
        if text is None:
            (run / "briefs" / name).unlink(missing_ok=True)
        else:
            (run / "briefs" / name).write_text(text, encoding="utf-8")


def check(channel):
    return invoke(channel, "check-files", "--step", "briefs")


def stage(run):
    return read_json(run / "run.json")["stage"]


def drop(text, prefix):
    return "\n".join(x for x in text.splitlines() if not x.startswith(prefix)) + "\n"


def test_three_kinds_are_green(channel, run):
    put(run)
    res = check(channel)
    assert res.exit_code == 0, res.output
    assert "Бриф 2 из 3: Shorts «Письмо начальнику за 40 секунд»" in res.output
    assert "Бриф 3 из 3: пост в Сообщество «Что разобрать дальше: таблицы или презентации»" in res.output
    assert "Проверено брифов: 3, ошибок нет" in res.output
    assert stage(run) == "брифы на решение"


def test_templates_have_empty_status_and_kind():
    for name, kind in (("brief-short.md", "Shorts"), ("brief-post.md", "пост в Сообщество")):
        text = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "\n- Статус:\n" in text and f"- Вид: {kind}\n" in text
    assert "\n- Статус:\n" in SHORT and "\n- Статус:\n" in POST


@pytest.mark.parametrize("field", ["Хук", "Идея", "Залёт", "Название 1", "Название 2",
                                   "Описание триггерное", "Описание SEO", "Хэштеги", "Теги",
                                   "Идея обложки", "Эмоции"])
def test_short_missing_field(channel, run, field):
    put(run, short=drop(SHORT, f"- {field}:"))
    res = check(channel)
    assert res.exit_code == 1 and "`briefs/02.md`" in res.output and f"нет поля «{field}»" in res.output
    assert stage(run) != "брифы на решение"


@pytest.mark.parametrize("field", ["Идея", "Залёт", "Формат", "Содержание", "Эмоции"])
def test_post_missing_field(channel, run, field):
    put(run, post=drop(POST, f"- {field}:"))
    res = check(channel)
    assert res.exit_code == 1 and "`briefs/03.md`" in res.output and f"нет поля «{field}»" in res.output


def test_short_script_rules(channel, run):
    put(run, short=SHORT.replace("[монтаж:", "[заметка:"))
    assert "в разделе «Сценарий» нет пометок по монтажу" in check(channel).output
    put(run, short=SHORT.replace("0:35–0:45", "1:35–1:45"))
    assert "сценарий идёт 105 с, нужно 30–60 с" in check(channel).output
    put(run, short=SHORT.replace("0:35–0:45", "0:25–0:29").replace("0:20–0:35", "0:15–0:25"))
    assert "сценарий идёт 29 с, нужно 30–60 с" in check(channel).output
    put(run, short=SHORT.replace("0:35–0:45", "0:35–1:00"))  # граница 60 с проходит
    assert check(channel).exit_code == 0
    put(run, short=SHORT.replace("0:35–0:45", "0:35–1:01"))
    assert "сценарий идёт 61 с" in check(channel).output
    put(run, short=SHORT.replace("0:05–0:20 ", ""))
    assert "нужны секунды" in check(channel).output
    put(run, short=drop(drop(SHORT, "- 0:35–0:45"), "- 0:20–0:35"))
    assert "в разделе «Сценарий» 2 строк, нужно не меньше 3" in check(channel).output


def test_post_text_must_be_ready(channel, run):
    put(run, post=POST.replace(POST_TEXT, "\n"))
    assert "раздел «Готовый текст» пустой" in check(channel).output
    put(run, post=POST.replace(POST_TEXT, "\n<текст поста>\n\n"))
    assert "не заполнен (остался шаблонный текст)" in check(channel).output
    put(run, post=POST.replace(POST_TEXT, "\n# Пояснение для автора\n\n"))
    assert "только текст поста" in check(channel).output
    put(run, post=POST.replace("## Готовый текст\n", "## Текст\n"))
    assert "нет раздела «Готовый текст»" in check(channel).output


def test_post_format_and_language(channel, run):
    put(run, post=POST.replace("- Формат: опрос", "- Формат: видео"))
    assert "формат «видео» не распознан" in check(channel).output
    english = "Hello everybody this is the whole post text written in plain English only"
    put(run, post=POST.replace(POST_TEXT, f"\n{english}\n\n"))
    assert "поле «Текст» не на языке брифа «ru»" in check(channel).output


def test_samples_are_real_for_short_and_post(channel, run):
    put(run, short=SHORT.replace("- demo_v07:", "- demo_v99:"))
    assert "`briefs/02.md`: образец `demo_v99` не залёт" in check(channel).output
    put(run, post=POST.replace("watch?v=demo_v07", "watch?v=other"))
    assert "`briefs/03.md`: у образца `demo_v07` ссылка" in check(channel).output
    put(run, post=drop(POST, "- demo_v07"))
    assert "нужно 2–3 образца" in check(channel).output
    put(run, short=SHORT.replace("- Залёт: demo_v01", "- Залёт: demo_v55"))
    assert "залёт `demo_v55` не найден" in check(channel).output


def test_status_must_be_empty_for_new_kinds(channel, run):
    put(run, short=SHORT.replace("- Статус:\n", "- Статус: принят\n"))
    res = check(channel)
    assert res.exit_code == 1 and "`briefs/02.md`, шапка: статус «принят» стоит до остановки" in res.output


@pytest.mark.parametrize("kwargs, expected", [
    ({"long": None}, "по `strategy.md` длинных видео 1, а брифов этого вида 0"),
    ({"short": None}, "по `strategy.md` Shorts 1, а брифов этого вида 0"),
    ({"post": None}, "по `strategy.md` постов в Сообщество 1, а брифов этого вида 0"),
])
def test_count_must_match_strategy(channel, run, kwargs, expected):
    put(run, **kwargs)
    res = check(channel)
    assert res.exit_code == 1 and expected in res.output
    assert stage(run) != "брифы на решение"


def test_extra_brief_is_over_count(channel, run):
    put(run)
    (run / "briefs" / "04.md").write_text(SHORT.replace("# Бриф 2:", "# Бриф 4:"), encoding="utf-8")
    res = check(channel)
    assert res.exit_code == 1 and "Shorts 1, а брифов этого вида 2" in res.output


def test_zero_in_strategy_means_no_briefs_of_kind(channel, run):
    text = (run / "strategy.md").read_text(encoding="utf-8")
    (run / "strategy.md").write_text(
        text.replace("Посты в Сообществе в месяц: 1", "Посты в Сообществе в месяц: 0"), encoding="utf-8")
    put(run)
    assert "постов в Сообщество 0, а брифов этого вида 1" in check(channel).output
    put(run, post=None)
    assert check(channel).exit_code == 0


def test_unreadable_strategy_balance_does_not_crash(channel, run):
    text = (run / "strategy.md").read_text(encoding="utf-8")
    (run / "strategy.md").write_text(text.replace("Shorts в месяц: 1", "Shorts в месяц: много"),
                                     encoding="utf-8")
    put(run)
    res = check(channel)
    assert "Traceback" not in res.output and res.exit_code == 0


def test_playbook_section_for_short_and_post():
    text = (ROOT / "playbooks" / "06-briefs-plan.md").read_text(encoding="utf-8")
    part = text.split("## Shorts и посты")[1].split("## Статусы и план")[0]
    for needle in ("templates/brief-short.md", "templates/brief-post.md", "30–60", "монтаж",
                   "Данных Сообщества в YouTube API нет", "Статус:", "strategy.md", "expected/briefs/02.md",
                   "expected/briefs/03.md"):
        assert needle in part, needle
