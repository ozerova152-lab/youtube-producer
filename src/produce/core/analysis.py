"""Проверка `analysis.md`: структура по шаблону `templates/analysis.md`, не смысл.

Скрипт сверяет файл с `virals.json` и `cache/comments.json`: все залёты разобраны,
числа комментариев правдивы, пометки «мало комментариев» и «причины предположительные»
стоят там, где данные их требуют. Качество рассуждений проверяет человек.
"""

import re

from produce.core import comments as comment_store
from produce.core import runs
from produce.core.errors import FileFormatError
from produce.core.files import read_json

FILE = "analysis.md"
MODE_COMMENTS = "комментарии"
MODE_TITLES = "названия и описания"
NOTE_GUESS = "Причины предположительные"
NOTE_FEW = "мало комментариев"
NO_EMOTIONS = {"нет", "—", "-", "–"}
HEADER_FIELDS = ["Язык разбора", "Основа разбора"]
VIDEO_FIELDS = ["Видео", "Комментариев разобрано", "Темы", "Эмоции", "Причина залёта"]

_SECTION = re.compile(r"^##\s+Залёт\s+(\d+)\s*:\s*(.*)$")
_FIELD = re.compile(r"^-\s+([^:]+?)\s*:\s*(.*)$")


def _fields(lines: list[str]) -> dict[str, str]:
    """Поля вида `- Имя: значение`; строки с отступом дописываются к значению."""
    found: dict[str, str] = {}
    current = None
    for line in lines:
        m = _FIELD.match(line)
        if m:
            current = m[1]
            found[current] = m[2].strip()
        elif current and line[:1] in (" ", "\t") and line.strip():
            found[current] = (found[current] + " " + line.strip().lstrip("-").strip()).strip()
        elif line.strip() and not line.startswith(">"):
            current = None
    return found


def _empty(value: str | None) -> bool:
    return value is None or not value.strip()


def _placeholder(value: str) -> bool:
    return bool(re.search(r"<[^>]+>", value))


def _read_virals(run: runs.Run) -> list[dict]:
    data = read_json(run.path / "virals.json")
    return list(data.get("virals", [])) if isinstance(data, dict) else []


def check(run: runs.Run, language: str, min_comments: int) -> list[str]:
    """Список проблем (пустой — файл в порядке). Каждая называет файл и место."""
    path = run.path / FILE
    if not path.exists():
        return [f"`{FILE}`: файла нет в {run.path}. Агент ещё не записал разбор"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [f"`{FILE}`: файл не читается, нужен текст в кодировке UTF-8"]
    try:
        virals = _read_virals(run)
        collected = comment_store.load(run)
    except FileFormatError as err:
        return [str(err)]

    problems: list[str] = []
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if _SECTION.match(line)]
    head = _fields(lines[: starts[0]] if starts else lines)

    for name in HEADER_FIELDS:
        if _empty(head.get(name)):
            problems.append(f"`{FILE}`, вверху файла: нет поля «{name}»")
        elif _placeholder(head[name]):
            problems.append(f"`{FILE}`, вверху файла: поле «{name}» не заполнено (остался шаблонный текст)")
    if not _empty(head.get("Язык разбора")) and head["Язык разбора"].strip() != language:
        problems.append(f"`{FILE}`, вверху файла: язык разбора «{head['Язык разбора'].strip()}», "
                        f"а язык сегмента «{language}»")

    has_comments = any(collected.get(str(v["id"])) for v in virals)
    expected = MODE_COMMENTS if has_comments else MODE_TITLES
    declared = (head.get("Основа разбора") or "").strip()
    if declared and declared != expected:
        problems.append(f"`{FILE}`, вверху файла: основа разбора «{declared}», "
                        f"а по `comments.json` должна быть «{expected}»")
    top = lines[: starts[0]] if starts else lines
    guess_note = any(line.lstrip("> ").startswith(NOTE_GUESS) for line in top)
    if expected == MODE_TITLES and not guess_note:
        problems.append(f"`{FILE}`, вверху файла: комментариев нет, но нет пометки «{NOTE_GUESS}»")
    if expected == MODE_COMMENTS and guess_note:
        problems.append(f"`{FILE}`, вверху файла: пометка «{NOTE_GUESS}» стоит, а комментарии есть")

    sections: dict[str, tuple[int, str, dict[str, str]]] = {}
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        m = _SECTION.match(lines[start])
        fields = _fields(lines[start + 1: end])
        vid = (fields.get("Видео") or "").strip()
        where = f"`{FILE}`, залёт {m[1]} «{m[2].strip()}»"
        if vid in sections:
            problems.append(f"{where}: видео `{vid}` разобрано дважды")
        sections[vid] = (int(m[1]), where, fields)

    for vid, (_, where, fields) in sections.items():
        problems += _check_section(vid, where, fields, collected, expected, min_comments)

    viral_ids = [str(v["id"]) for v in virals]
    for vid in viral_ids:
        if vid not in sections:
            problems.append(f"`{FILE}`: нет разбора для залёта `{vid}`")
    for vid in sections:
        if vid and vid not in viral_ids:
            problems.append(f"{sections[vid][1]}: видео `{vid}` не залёт, в `virals.json` его нет")
    return problems


def _check_section(vid: str, where: str, fields: dict[str, str], collected: dict,
                   mode: str, min_comments: int) -> list[str]:
    problems = []
    for name in VIDEO_FIELDS:
        if name not in fields:
            problems.append(f"{where}: нет поля «{name}»")
        elif _empty(fields[name]):
            problems.append(f"{where}: поле «{name}» пустое")
        elif _placeholder(fields[name]):
            problems.append(f"{where}: поле «{name}» не заполнено (остался шаблонный текст)")
    if problems:
        return problems

    real = len(collected.get(vid) or [])
    try:
        stated = int(fields["Комментариев разобрано"].replace(" ", ""))
    except ValueError:
        return [f"{where}: в поле «Комментариев разобрано» нужно число, а там «{fields['Комментариев разобрано']}»"]
    if stated != real:
        problems.append(f"{where}: в поле «Комментариев разобрано» {stated}, а в `comments.json` {real}")

    emotions = fields["Эмоции"].strip().rstrip(".").lower()
    few = NOTE_FEW in (fields.get("Пометка") or "").lower()
    if mode == MODE_COMMENTS and real < min_comments:
        if not few:
            problems.append(f"{where}: комментариев {real} (меньше {min_comments}), "
                            f"нужна строка «- Пометка: {NOTE_FEW}»")
        if emotions not in NO_EMOTIONS:
            problems.append(f"{where}: при малом числе комментариев эмоций нет, в поле «Эмоции» должно быть «нет»")
    elif mode == MODE_COMMENTS:
        if few:
            problems.append(f"{where}: пометка «{NOTE_FEW}» стоит, а комментариев {real}")
        if emotions in NO_EMOTIONS:
            problems.append(f"{where}: комментариев {real}, поле «Эмоции» не должно быть пустым по смыслу")
    elif emotions not in NO_EMOTIONS:
        problems.append(f"{where}: разбор без комментариев, в поле «Эмоции» должно быть «нет»")
    return problems
