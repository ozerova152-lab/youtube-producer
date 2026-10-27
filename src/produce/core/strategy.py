"""Проверка `strategy.md`: структура по шаблону и строка статуса, не смысл.

Статус — отдельная строка «Статус: черновик» или «Статус: утверждена». «Утверждена» ставит
только человек, правкой файла; скрипт лишь читает строку и двигает этап запуска. Разбор строки
строгий (один пробел, строчные буквы): так опечатка не превратится молча в «утверждена».
Скрипт сверяет стратегию с данными запуска (мои ролики из `my_results.json`, залёты из
`virals.json`); качество выводов проверяет человек.
"""

import re

from produce.core import runs
from produce.core.errors import FileFormatError
from produce.core.files import read_json
from produce.core.niche import _fields, _placeholders, _read, _split

STRATEGY = "strategy.md"
DRAFT = "черновик"
APPROVED = "утверждена"

MSG_DRAFT = "В файле статус «черновик». Замените его сами и напишите «готово». Дальше не иду"
MSG_APPROVED = "Стратегия утверждена, перехожу к брифам"

INPUTS = ["Тема канала", "Цель", "Аудитория", "Время и силы в неделю"]
EVIDENCE = ["Мои лучшие ролики", "Мои слабые ролики", "Залёты ниши", "Что показал разбор"]
BALANCE = ["Длинные видео в месяц", "Shorts в месяц", "Посты в Сообществе в месяц",
           "Почему такой баланс"]
FREQUENCY = ["Роликов в месяц", "Ритм публикаций"]
SECTIONS = {"Вводные": INPUTS, "Опора на данные": EVIDENCE, "Баланс форматов": BALANCE,
            "Частота": FREQUENCY}

_STATUS_LINE = re.compile(r"^[\s>*\-]*статус\s*:", re.IGNORECASE)
_STATUS_OK = re.compile(rf"^Статус: ({DRAFT}|{APPROVED})$")
_NUMBER = re.compile(r"^(\d+)\b")


def read_status(run: runs.Run) -> tuple[str | None, list[str]]:
    """Статус из строки файла и проблемы формата (статус None — не распознан)."""
    lines, problems = _read(run, STRATEGY)
    if lines is None:
        return None, problems
    found = [(n, line) for n, line in enumerate(lines, start=1) if _STATUS_LINE.match(line)]
    if not found:
        return None, [f"`{STRATEGY}`: нет строки статуса. Добавьте строку «Статус: {DRAFT}»"]
    if len(found) > 1:
        return None, [f"`{STRATEGY}`, строка {n}: вторая строка статуса, должна быть одна"
                      for n, _ in found[1:]]
    n, line = found[0]
    m = _STATUS_OK.match(line)
    if not m:
        return None, [(f"`{STRATEGY}`, строка {n}: статус «{line}» не распознан. "
                       f"Допустимо ровно «Статус: {DRAFT}» или «Статус: {APPROVED}» "
                       "(один пробел, строчные буквы, без лишнего в строке)")]
    return m[1], []


def _load(run: runs.Run, name: str) -> dict | None:
    path = run.path / name
    if not path.exists():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def _count(fields: dict[str, str], name: str, where: str) -> tuple[int | None, list[str]]:
    value = fields.get(name, "")
    if not value or _placeholders(STRATEGY, where, fields, [name]):
        return None, []  # поле пустое или шаблонное: об этом уже сказано
    m = _NUMBER.match(value)
    if not m:
        return None, [f"`{STRATEGY}`, {where}: в поле «{name}» нужно число, а там «{value}»"]
    return int(m[1]), []


def check(run: runs.Run) -> tuple[str | None, list[str]]:
    """Статус и проблемы `strategy.md` (пустой список проблем — файл в порядке)."""
    status, problems = read_status(run)
    lines, read_problems = _read(run, STRATEGY)
    if lines is None:
        return None, read_problems
    head, sections = _split(lines, "##")
    head_fields = _fields(head)
    problems += _placeholders(STRATEGY, "вверху файла", head_fields, ["Запуск"])

    by_title = dict(sections)
    fields_of: dict[str, dict[str, str]] = {}
    for title, required in SECTIONS.items():
        if title not in by_title:
            problems.append(f"`{STRATEGY}`: нет раздела «{title}»")
            continue
        fields_of[title] = _fields(by_title[title])
        problems += _placeholders(STRATEGY, f"раздел «{title}»", fields_of[title], required)

    balance, freq = fields_of.get("Баланс форматов"), fields_of.get("Частота")
    if balance is not None and freq is not None:
        where_b, where_f = "раздел «Баланс форматов»", "раздел «Частота»"
        long_n, p1 = _count(balance, "Длинные видео в месяц", where_b)
        short_n, p2 = _count(balance, "Shorts в месяц", where_b)
        _, p3 = _count(balance, "Посты в Сообществе в месяц", where_b)
        total, p4 = _count(freq, "Роликов в месяц", where_f)
        problems += p1 + p2 + p3 + p4
        if None not in (long_n, short_n, total) and total != long_n + short_n:
            problems.append(
                f"`{STRATEGY}`, {where_f}: «Роликов в месяц» {total}, а длинных и Shorts вместе "
                f"{long_n + short_n}")

    if "Опора на данные" in fields_of:
        problems += _check_evidence(run, fields_of["Опора на данные"])
    return status, problems


def _check_evidence(run: runs.Run, fields: dict[str, str]) -> list[str]:
    """Стратегия опирается на мои лучшие и слабые ролики и на залёты запуска."""
    where = "раздел «Опора на данные»"
    problems: list[str] = []
    try:
        mine = _load(run, "my_results.json")
        viral_data = _load(run, "virals.json")
    except FileFormatError as err:
        return [str(err)]
    if mine and mine.get("status") == "ok":
        for field, key in (("Мои лучшие ролики", "best"), ("Мои слабые ролики", "weak")):
            value = fields.get(field, "")
            if not value or _placeholders(STRATEGY, where, fields, [field]):
                continue
            missing = [v["id"] for v in mine.get(key, []) if v["id"] not in value]
            if missing:
                problems.append(f"`{STRATEGY}`, {where}: в поле «{field}» не названы ролики "
                                f"из `my_results.json`: {', '.join(missing)}")
    virals = [str(v["id"]) for v in (viral_data or {}).get("virals", [])]
    value = fields.get("Залёты ниши", "")
    if virals and value and not _placeholders(STRATEGY, where, fields, ["Залёты ниши"]) \
            and not any(i in value for i in virals):
        problems.append(f"`{STRATEGY}`, {where}: в поле «Залёты ниши» нет ни одного id из "
                        f"`virals.json` ({', '.join(virals)})")
    return problems


def gate(run: runs.Run) -> list[str]:
    """Пускает к брифам и плану только при статусе «утверждена»; иначе список причин отказа."""
    status, problems = read_status(run)
    if problems:
        return problems
    if status != APPROVED:
        return [MSG_DRAFT]
    return []
