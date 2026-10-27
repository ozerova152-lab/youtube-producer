"""Мои результаты: лучшие и слабые ролики моего канала — для сбора (кассеты) и для импорта."""

import pytest
import yaml
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json

RUN = "2026-10_ru_v1"
CANARY = "CANARY-KEY-do-not-leak-7f3a9c"


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def set_my_channel(channel, value):
    path = channel / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if value is None:
        data["channel"].pop("my_channel_id", None)
    else:
        data["channel"]["my_channel_id"] = value
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def invoke(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args])


def collect_and_report(channel, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"YOUTUBE_API_KEY={CANARY}\n", encoding="utf-8")
    done = invoke(channel, "collect", "--segment", "ru", "--env-file", str(env), "--confirm")
    assert done.exit_code == 0, done.output
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0
    rep = invoke(channel, "report", "--segment", "ru")
    assert rep.exit_code == 0, rep.output
    return (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")


def section(text):
    return text.split("## Мои результаты", 1)[1]


@pytest.mark.vcr("collect_ru.yaml")
def test_collect_report_names_best_and_weak(channel, tmp_path):
    text = collect_and_report(channel, tmp_path)
    mine = section(text)
    assert "### Мои лучшие ролики" in mine and "### Мои слабые ролики" in mine
    # Лучший ролик демо-канала: 90 000 просмотров, 5 400 лайков, 610 комментариев.
    best_row = next(line for line in mine.splitlines() if "заменил ассистента" in line)
    assert "| 90 000 | 5 400 | 610 |" in best_row
    weak_part = mine.split("### Мои слабые ролики")[1]
    assert "Обзор новых моделей" in weak_part and "| 4 500 | 120 | 12 |" in weak_part
    # Чужие ролики в мои результаты не попадают.
    assert "Промпт-лаб" not in mine and "ChatGPT tutorial на русском" not in mine
    saved = read_json(channel / "runs" / RUN / "my_results.json")
    assert saved["status"] == "ok" and saved["videos"] == 6
    assert saved["best"][0]["views"] == 90000 and saved["weak"][0]["views"] == 4500
    # Лучшие идут по убыванию, слабые от самого слабого; пересечений нет.
    assert [v["views"] for v in saved["best"]] == sorted((v["views"] for v in saved["best"]), reverse=True)
    assert not {v["id"] for v in saved["best"]} & {v["id"] for v in saved["weak"]}
    assert CANARY not in text


@pytest.mark.vcr("collect_ru.yaml")
def test_collect_without_my_channel_marks_and_goes_on(channel, tmp_path):
    set_my_channel(channel, None)
    # Те же запросы, что и с каналом: он уже среди авторов выдачи, кассета не менялась.
    text = collect_and_report(channel, tmp_path)
    assert "## Мои результаты\n\nМой канал не задан, пропускаю." in text
    assert "## Залёты" in text
    assert read_json(channel / "runs" / RUN / "my_results.json")["status"] == "not_set"


def test_empty_my_channel_value_is_not_set(channel):
    set_my_channel(channel, "  ")
    assert invoke(channel, "import", str(DEMO / "import.csv"), "--segment", "ru").exit_code == 0
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert "Мой канал не задан, пропускаю" in section(text)


def test_import_report_has_my_results(channel):
    result = invoke(channel, "import", str(DEMO / "import.csv"), "--segment", "ru")
    assert result.exit_code == 0, result.output
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    mine = section(text)
    assert "### Мои лучшие ролики" in mine
    assert "Как использовать нейросеть: выпуск 1" in mine and "| 52 000 | 1 733 | 173 |" in mine
    assert "Обращений к YouTube: 0" in result.output


def test_import_without_my_channel_is_skipped_with_note(channel):
    set_my_channel(channel, "UC_not_in_file")
    assert invoke(channel, "import", str(DEMO / "import.csv"), "--segment", "ru").exit_code == 0
    assert invoke(channel, "virals", "--segment", "ru").exit_code == 0
    rep = invoke(channel, "report", "--segment", "ru")
    assert rep.exit_code == 0, rep.output
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    assert "Моего канала нет в файле импорта, пропускаю" in section(text)
    assert "## Залёты" in text  # поток идёт дальше
    assert read_json(channel / "runs" / RUN / "my_results.json")["status"] == "not_found"


def test_import_keeps_my_small_channel(channel, tmp_path):
    # У моего канала 2 ролика: обычный канал с менее чем 5 роликами пропускается, мой — нет.
    csv_text = (DEMO / "import.csv").read_text(encoding="utf-8").splitlines()
    head = csv_text[0]
    extra = [
        "my1,Мой первый,,UC_mine,Мой,300,2026-10-01T10:00:00Z,600,нет,700,30,4",
        "my2,Мой второй,,UC_mine,Мой,300,2026-10-10T10:00:00Z,600,нет,200,5,,",
    ]
    extra[1] = "my2,Мой второй,,UC_mine,Мой,300,2026-10-10T10:00:00Z,600,нет,200,5,0"
    file = tmp_path / "mine.csv"
    file.write_text("\n".join([head, *csv_text[1:], *extra]) + "\n", encoding="utf-8")
    set_my_channel(channel, "UC_mine")
    assert invoke(channel, "import", str(file), "--segment", "ru").exit_code == 0
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    saved = read_json(channel / "runs" / RUN / "my_results.json")
    assert saved["status"] == "ok" and saved["videos"] == 2
    assert saved["best"][0]["title"] == "Мой первый" and saved["weak"][0]["title"] == "Мой второй"


def test_title_with_pipe_does_not_break_table(channel, tmp_path):
    # Название — чужой текст (данные): `|` и перевод строки не ломают таблицу.
    rows = ["id,title,channel_id,channel_title,channel_subscribers,published_at,views,likes,comments"]
    for i in range(6):
        title = '"Плохое | название с переводом"' if i == 0 else f"Ролик {i}"
        rows.append(f"m{i},{title},UC_mine,Мой,100,2026-10-{10 + i:02d}T10:00:00Z,{1000 * (6 - i)},10,1")
    file = tmp_path / "pipe.csv"
    file.write_text("\n".join(rows) + "\n", encoding="utf-8")
    set_my_channel(channel, "UC_mine")
    assert invoke(channel, "import", str(file), "--segment", "ru").exit_code == 0
    assert invoke(channel, "report", "--segment", "ru").exit_code == 0
    text = (channel / "runs" / RUN / "report.md").read_text(encoding="utf-8")
    row = next(line for line in section(text).splitlines() if "Плохое" in line)
    assert row.count("|") == 6 and "Плохое / название с переводом" in row
