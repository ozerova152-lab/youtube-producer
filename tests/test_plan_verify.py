"""T13, независимая проверка: статусы брифов и месячный план (`check-files --step plan`).

Критерии берутся из задачи T13 и потока 4 спеки, а не из кода. Сети и ключа нет.
"""

import hashlib
import re

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json, write_json_atomic

RUN = "2026-10_ru_v1"
EXP = DEMO / "expected"
DECIDED = {p.name: p.read_text(encoding="utf-8") for p in sorted((EXP / "briefs_decided").glob("*.md"))}
PLAN = (EXP / "plan.md").read_text(encoding="utf-8")
STRATEGY = (EXP / "strategy_three_briefs.md").read_text(encoding="utf-8")
ROOT = DEMO.parent.parent
TITLES = {  # название и вид из образцов
    "01": ("длинное видео", "Нейросеть для таблиц без формул"),
    "02": ("Shorts", "Письмо начальнику за 40 секунд"),
    "03": ("пост в Сообщество", "Что разобрать дальше: таблицы или презентации"),
    "04": ("длинное видео", "Три ошибки новичка в первом запросе к нейросети"),
    "05": ("Shorts", "Один вопрос нейросети, который экономит час"),
}


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def invoke(channel, *args):
    return CliRunner().invoke(app, ["--channel", str(channel), *args, "--segment", "ru"])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(run):
    return read_json(run / "run.json")["stage"]


def set_status_line(text, line):
    return re.sub(r"^- Статус:.*$", line, text, count=1, flags=re.MULTILINE)


def set_limits(channel, lo, hi):
    f = channel / "settings.yaml"
    t = f.read_text(encoding="utf-8")
    t = re.sub(r"min_videos_per_month: \d+", f"min_videos_per_month: {lo}", t)
    t = re.sub(r"max_videos_per_month: \d+", f"max_videos_per_month: {hi}", t)
    f.write_text(t, encoding="utf-8")


def make_plan(numbers, weeks=None, count=None, limits="2–12"):
    """plan.md по образцу: numbers раскладываются по неделям (по умолчанию по 2)."""
    weeks = weeks or [numbers[i:i + 2] for i in range(0, len(numbers), 2)]
    shown = count if count is not None else len(numbers)
    out = ["# План месяца\n\n- Запуск: 2026-10, сегмент ru\n",
           f"- Принятых брифов: {shown}\n- Пределы из настроек: {limits}\n"]
    for i, group in enumerate(weeks, 1):
        out.append(f"\n## Неделя {i}\n\n")
        for n in group:
            kind, title = TITLES[f"{n:02d}"]
            out.append(f"- Бриф {n} ({kind}): «{title}» — `briefs/{n:02d}.md`\n")
    return "".join(out)


@pytest.fixture
def run(channel):
    """Запуск на «брифы на решение»: пять брифов 01–05 без статусов."""
    assert invoke(channel, "import", str(DEMO / "import_comments.json")).exit_code == 0
    assert invoke(channel, "virals").exit_code == 0
    path = channel / "runs" / RUN
    (path / "strategy.md").write_text(
        STRATEGY.replace("Статус: черновик", "Статус: утверждена"), encoding="utf-8")
    (path / "briefs").mkdir()
    for n in range(1, 6):
        (path / "briefs" / f"{n:02d}.md").write_text(
            set_status_line(DECIDED[f"{n:02d}.md"], "- Статус:"), encoding="utf-8")
    # 5 брифов при strategy на 3: на шаге «брифы» «ровно» применимо, поэтому подгоняем стратегию
    res = invoke(channel, "check-files", "--step", "briefs")
    if res.exit_code != 0:
        for n in (4, 5):
            (path / "briefs" / f"0{n}.md").unlink()
        res = invoke(channel, "check-files", "--step", "briefs")
        assert res.exit_code == 0, res.output
        for n in (4, 5):
            (path / "briefs" / f"0{n}.md").write_text(
                set_status_line(DECIDED[f"0{n}.md"], "- Статус:"), encoding="utf-8")
    assert stage(path) == "брифы на решение"
    return path


def setst(run, **vals):
    for n, v in vals.items():
        f = run / "briefs" / f"{n}.md"
        f.write_text(set_status_line(f.read_text(encoding="utf-8"), f"- Статус: {v}".rstrip()),
                     encoding="utf-8")


def plan_check(channel):
    return invoke(channel, "check-files", "--step", "plan")


def snapshot(run):
    return {p.name: sha(p) for p in (run / "briefs").glob("*.md")}


# --- критерий 1: стратегия не утверждена ---------------------------------------------------

def test_c1_draft_strategy_refused(channel, run):
    (run / "strategy.md").write_text(STRATEGY, encoding="utf-8")
    res = plan_check(channel)
    assert res.exit_code == 1 and "черновик" in res.output and "Traceback" not in res.output
    assert stage(run) == "брифы на решение" and not (run / "plan.md").exists()


def test_c1_no_strategy_file_refused(channel, run):
    (run / "strategy.md").unlink()
    res = plan_check(channel)
    assert res.exit_code == 1 and "strategy.md" in res.output and "Traceback" not in res.output


def test_stage_before_briefs_refused(channel, run):
    setst(run, **{"01": "принят", "02": "принят"})
    (run / "plan.md").write_text(make_plan([1, 2]), encoding="utf-8")
    d = read_json(run / "run.json")
    d["stage"] = "стратегия утверждена"
    write_json_atomic(run / "run.json", d)
    res = plan_check(channel)
    assert res.exit_code == 1 and "Сначала брифы" in res.output
    assert stage(run) == "стратегия утверждена"


# --- критерий 8: пустые статусы -----------------------------------------------------------

def test_c8_two_of_five_empty_named_exactly(channel, run):
    setst(run, **{"01": "принят", "03": "принят", "04": "отклонён"})
    h = snapshot(run)
    res = plan_check(channel)
    assert res.exit_code == 1 and res.output.strip() == "Нет статуса: 2, 5"
    assert not (run / "plan.md").exists() and snapshot(run) == h


def test_c8_all_empty_names_all(channel, run):
    assert plan_check(channel).output.strip() == "Нет статуса: 1, 2, 3, 4, 5"


# --- критерий 6: неверные строки статуса --------------------------------------------------

@pytest.mark.parametrize("bad", ["Принят", "ПРИНЯТ", "принят.", "Принят.", " принят принят",
                                 "принят, позже", "ok", "да"])
def test_c6_bad_status_values(channel, run, bad):
    setst(run, **{"01": "принят", "02": "принят", "03": "принят", "04": "отклонён", "05": "позже"})
    setst(run, **{"03": bad})
    h = snapshot(run)
    res = plan_check(channel)
    assert res.exit_code == 1 and "briefs/03.md" in res.output and "статус" in res.output
    assert snapshot(run) == h and stage(run) == "брифы на решение"


def test_c6_two_status_lines_and_no_status_line(channel, run):
    setst(run, **{"01": "принят", "02": "принят", "03": "принят", "04": "отклонён", "05": "позже"})
    f = run / "briefs" / "02.md"
    t = f.read_text(encoding="utf-8")
    f.write_text(t.replace("- Статус: принят", "- Статус: принят\n- Статус: отклонён", 1), encoding="utf-8")
    h = sha(f)
    res = plan_check(channel)
    assert res.exit_code == 1 and "briefs/02.md" in res.output and sha(f) == h
    f.write_text(re.sub(r"^- Статус:.*\n", "", t, flags=re.MULTILINE), encoding="utf-8")
    h = sha(f)
    res = plan_check(channel)
    assert res.exit_code == 1 and "briefs/02.md" in res.output and "Traceback" not in res.output
    assert sha(f) == h


def test_c6_whitespace_around_valid_value_is_tolerated_or_named(channel, run):
    # Допустимо и то и другое, но не падение и не молчаливая порча файла.
    setst(run, **{"01": "  принят  "})
    h = snapshot(run)
    res = plan_check(channel)
    assert "Traceback" not in res.output and snapshot(run) == h


# --- критерии 4, 5, 3: пределы ------------------------------------------------------------

def accepted_n(run, n):
    setst(run, **{f"0{i}": ("принят" if i <= n else "позже") for i in range(1, 6)})


@pytest.mark.parametrize("lo,hi,n", [(2, 3, 2), (2, 3, 3), (3, 3, 3), (1, 5, 5), (1, 5, 1)])
def test_c3_at_limits_green(channel, run, lo, hi, n):
    set_limits(channel, lo, hi)
    accepted_n(run, n)
    nums = list(range(1, n + 1))
    (run / "plan.md").write_text(make_plan(nums, limits=f"{lo}–{hi}"), encoding="utf-8")
    res = plan_check(channel)
    assert res.exit_code == 0, res.output
    assert f"план из {n} принятых брифов, пределы {lo}–{hi}" in res.output
    assert stage(run) == "план готов"


@pytest.mark.parametrize("lo,n", [(3, 2), (4, 3), (2, 1)])
def test_c4_shortage_exact_text_no_fill_no_change(channel, run, lo, n):
    set_limits(channel, lo, lo + 5)
    accepted_n(run, n)
    h, s = snapshot(run), sha(channel / "settings.yaml")
    res = plan_check(channel)
    assert res.exit_code == 1
    assert res.output.strip() == (
        f"Принятых {n}, минимум {lo}. Нехватка: {lo - n}. План не добит. Могу сделать ещё брифы "
        "или вы смените статус «позже» на «принят»")
    assert snapshot(run) == h and sha(channel / "settings.yaml") == s
    assert not (run / "plan.md").exists() and stage(run) == "брифы на решение"


@pytest.mark.parametrize("hi,n", [(2, 3), (3, 4), (1, 5)])
def test_c5_excess_exact_text_nothing_cut(channel, run, hi, n):
    set_limits(channel, 1, hi)
    accepted_n(run, n)
    h = snapshot(run)
    res = plan_check(channel)
    assert res.exit_code == 1
    assert res.output.strip() == (f"Принятых {n}, максимум {hi}. Перенесите лишние в «позже» "
                                  "и напишите «готово»")
    assert snapshot(run) == h and not (run / "plan.md").exists()
    assert stage(run) == "брифы на решение"


def test_zero_accepted_is_shortage_not_green(channel, run):
    setst(run, **{f"0{i}": "отклонён" for i in range(1, 6)})
    res = plan_check(channel)
    assert res.exit_code == 1 and "Принятых 0, минимум 2" in res.output


# --- критерий 2 и 3: состав плана ---------------------------------------------------------

def base_green(channel, run):
    setst(run, **{"01": "принят", "02": "принят", "03": "принят", "04": "отклонён", "05": "позже"})
    (run / "plan.md").write_text(PLAN, encoding="utf-8")


def test_c3_demo_sample_green_and_only_accepted(channel, run):
    base_green(channel, run)
    res = plan_check(channel)
    assert res.exit_code == 0, res.output
    assert "Месяц готов. Публикацию делаете вы" in res.output
    txt = (run / "plan.md").read_text(encoding="utf-8")
    assert "briefs/04.md" not in txt and "briefs/05.md" not in txt
    assert snapshot(run)["04.md"] == sha(ROOT / "examples/demo/expected/briefs_decided/04.md")


def test_c2_status_flip_to_rejected_makes_plan_red(channel, run):
    base_green(channel, run)
    assert plan_check(channel).exit_code == 0
    setst(run, **{"03": "отклонён"})
    res = plan_check(channel)
    assert res.exit_code == 1 and "бриф 3" in res.output


@pytest.mark.parametrize("name,mutate,expect", [
    ("weeks_gap", lambda: make_plan([1, 2, 3], weeks=[[1, 2], [3]]).replace("Неделя 2", "Неделя 3"),
     "Неделя"),
    ("weeks_start_2", lambda: make_plan([1, 2, 3], weeks=[[1, 2], [3]]).replace(
        "Неделя 1", "Неделя 2").replace("Неделя 2\n\n- Бриф 3", "Неделя 3\n\n- Бриф 3"), "Неделя"),
    ("empty_week", lambda: make_plan([1, 2, 3], weeks=[[1, 2], [3]]) + "\n## Неделя 3\n", "Неделя 3"),
    ("count_mismatch", lambda: make_plan([1, 2, 3], count=4), "Принятых брифов"),
    ("limits_mismatch", lambda: make_plan([1, 2, 3], limits="4–8"), "пределы"),
    ("wrong_kind", lambda: make_plan([1, 2, 3]).replace("(Shorts)", "(длинное видео)"), "бриф 2"),
    ("wrong_title", lambda: make_plan([1, 2, 3]).replace("Письмо начальнику", "Письмо боссу"),
     "бриф 2"),
    ("dup", lambda: make_plan([1, 2, 3, 1], weeks=[[1, 2], [3, 1]]), "2 раза"),
    ("missing", lambda: make_plan([1, 2], count=3), "нет принятых брифов: 3"),
    ("unknown_brief", lambda: make_plan([1, 2, 3]) + "- Бриф 9 (Shorts): «X» — `briefs/09.md`\n",
     "бриф 9"),
])
def test_plan_mutations_red(channel, run, name, mutate, expect):
    setst(run, **{"01": "принят", "02": "принят", "03": "принят", "04": "отклонён", "05": "позже"})
    (run / "plan.md").write_text(mutate(), encoding="utf-8")
    res = plan_check(channel)
    assert res.exit_code == 1, (name, res.output)
    assert expect in res.output, (name, res.output)
    assert stage(run) == "брифы на решение"


@pytest.mark.parametrize("content", [b"", b"   \n\n", b"\xff\xfe\x00\x80 not utf8 \xc3\x28"])
def test_plan_empty_or_binary_is_red_without_traceback(channel, run, content):
    base_green(channel, run)
    (run / "plan.md").write_bytes(content)
    res = plan_check(channel)
    assert res.exit_code == 1 and "Traceback" not in res.output
    assert stage(run) == "брифы на решение"


def test_plan_missing_is_red(channel, run):
    setst(run, **{"01": "принят", "02": "принят", "03": "позже", "04": "позже", "05": "позже"})
    res = plan_check(channel)
    assert res.exit_code == 1 and "plan.md" in res.output and stage(run) == "брифы на решение"


# --- критерий 7: этап --------------------------------------------------------------------

def test_c7_stage_only_after_green_and_red_does_not_erase(channel, run):
    base_green(channel, run)
    assert stage(run) == "брифы на решение"
    assert plan_check(channel).exit_code == 0 and stage(run) == "план готов"
    setst(run, **{"03": "отклонён"})
    assert plan_check(channel).exit_code == 1
    assert stage(run) == "план готов"  # красная не стирает достигнутое
    assert plan_check(channel).exit_code == 1


def test_settings_unchanged_on_all_outcomes(channel, run):
    s = sha(channel / "settings.yaml")
    plan_check(channel)
    base_green(channel, run)
    plan_check(channel)
    setst(run, **{"03": "xx"})
    plan_check(channel)
    assert sha(channel / "settings.yaml") == s


def test_briefs_step_green_after_statuses(channel, run):
    setst(run, **{"01": "принят", "02": "принят", "03": "принят", "04": "отклонён", "05": "позже"})
    h = snapshot(run)
    res = invoke(channel, "check-files", "--step", "briefs")
    # В зелёную при тех же файлах: число «ровно» относится к первому набору; допустимо только
    # если 5 файлов совпадают со стратегией. Главное: статусы сами не делают шаг красным.
    assert "статус" not in res.output.lower() or res.exit_code == 0, res.output
    assert snapshot(run) == h


def test_idempotent_green(channel, run):
    base_green(channel, run)
    a = plan_check(channel)
    b = plan_check(channel)
    assert a.exit_code == b.exit_code == 0 and stage(run) == "план готов"


# --- сценарий (структура) -----------------------------------------------------------------

def test_playbook_pause_and_prohibitions():
    t = (ROOT / "playbooks/06-briefs-plan.md").read_text(encoding="utf-8")
    sec = t.split("## Статусы и план", 1)[1].split("\n## ", 1)[0]
    low = sec.lower()
    assert "остановка на решение" in low
    assert "агент статусы не ставит" in low
    assert "ничего не резать" in low and "не добивать" in low
    assert "нет статуса: 2, 5" in low
    assert "руками его не ставить" in low
    assert "settings.yaml" in t and "ничего не опубликовано" in t.lower()
    assert "не перезаписывать" in low
    for ph in ("«принят»", "«отклонён»", "«позже»"):
        assert ph in sec
    assert "check-files --step plan" in sec
    # Заголовки не ослаблены
    assert "## Shorts и посты" in t and "## Статусы и план" in t


def test_template_and_sample_exist():
    assert (ROOT / "templates/plan.md").is_file() and (EXP / "plan.md").is_file()
    assert sorted(p.name for p in (EXP / "briefs_decided").glob("*.md")) == [
        f"0{i}.md" for i in range(1, 6)]
    st = [re.search(r"^- Статус: (.*)$", DECIDED[f"0{i}.md"], re.MULTILINE).group(1)
          for i in range(1, 6)]
    assert st == ["принят", "принят", "принят", "отклонён", "позже"]


def test_edits_to_old_tests_not_weakened():
    """Законность правок исполнителя в test_briefs*.py: удалены только проверки слов T12/T13."""
    import subprocess
    diff = subprocess.run(["git", "diff", "-U0", "--", "tests/test_briefs.py",
                           "tests/test_briefs_verify.py"], check=False, cwd=ROOT,
                          capture_output=True, text=True).stdout
    if not diff:  # уже закоммичено — проверять нечего
        return
    removed = [x for x in diff.splitlines() if x.startswith("-") and not x.startswith("---")]
    added = "\n".join(x for x in diff.splitlines() if x.startswith("+"))
    assert any("ещё не подключена" in x for x in removed)
    assert '"## Shorts и посты" in low' in added and '"## Статусы и план" in low' in added
    # из убранных утверждений допустимы только заглушки шага plan и слова T12/T13
    for x in removed:
        if "assert" in x:
            assert ("ещё не подключена" in x or "T12" in x or "T13" in x), x


# --- круг 2: края правила «одна строка статуса» --------------------------------------------

def _all_valid(run):
    setst(run, **{"01": "принят", "02": "принят", "03": "принят", "04": "отклонён", "05": "позже"})


@pytest.mark.parametrize("extra", [
    "- Статус: принят\n- Статус: принят",  # две одинаковые
    "- Статус:\n- Статус:",  # две пустые
    "- Статус: принят\n- Статус: отклонён\n- Статус: позже",  # три
])
@pytest.mark.parametrize("step", ["plan", "briefs"])
def test_r2_multiple_status_lines_red_both_steps(channel, run, extra, step):
    _all_valid(run)
    f = run / "briefs" / "02.md"
    f.write_text(re.sub(r"^- Статус:.*$", extra, f.read_text(encoding="utf-8"), count=1,
                        flags=re.MULTILINE), encoding="utf-8")
    h = sha(f)
    res = invoke(channel, "check-files", "--step", step)
    assert res.exit_code == 1 and "briefs/02.md" in res.output and "Статус" in res.output
    assert "Traceback" not in res.output and sha(f) == h
    assert stage(run) == "брифы на решение"


def test_r2_status_line_outside_header_is_not_a_second_status(channel, run):
    _all_valid(run)
    (run / "plan.md").write_text(PLAN, encoding="utf-8")
    f = run / "briefs" / "02.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n- Статус: отклонён\n", encoding="utf-8")
    res = plan_check(channel)
    assert "Traceback" not in res.output
    # статус берётся из шапки: бриф 2 остаётся принятым, план с ним зелёный
    assert res.exit_code == 0, res.output
