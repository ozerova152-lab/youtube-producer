"""Проверка `covers.md`: структура по шаблону `templates/covers.md`, не смысл.

Скрипт сверяет файл с `virals.json`: каждый залёт разобран ровно в одном блоке, id
настоящие, число «к норме канала» совпадает с `times_norm`, пустых и шаблонных значений
нет. Картинки скрипт не скачивает и не смотрит: описание обложки — предположение агента,
качество описания проверяет человек.
"""

import re

from produce.core import runs
from produce.core.analysis import _SECTION, _empty, _fields, _placeholder
from produce.core.errors import FileFormatError
from produce.core.files import read_json

FILE = "covers.md"
THUMBS_DIR = "thumbs"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MODE_LINKS = "обложки по ссылкам"
MODE_FOLDER = "обложки из папки thumbs"
MODE_NONE = "нет данных"
MODES = (MODE_LINKS, MODE_FOLDER, MODE_NONE)
NOTE_GUESS = "предположение агента"
BLOCK_FIELDS = ["Видео", "К норме канала", "Текст на обложке", "Лица", "Цвет", "Композиция"]
SUMMARY_HEADINGS = ["Общие закономерности", "Связь с просмотрами"]

_HEADING = re.compile(r"^##\s+(.*?)\s*$")


def _read_virals(run: runs.Run) -> list[dict]:
    data = read_json(run.path / "virals.json")
    return list(data.get("virals", [])) if isinstance(data, dict) else []


def _number(value: str) -> float | None:
    m = re.search(r"\d+(?:[.,]\d+)?", value.replace(" ", ""))
    return float(m[0].replace(",", ".")) if m else None


def has_images(run: runs.Run) -> bool:
    folder = run.path / THUMBS_DIR
    return folder.is_dir() and any(
        p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES for p in folder.iterdir())


def analyzed_ids(run: runs.Run) -> set[str] | None:
    """id залётов, разобранных в блоках `covers.md`; None, если файла нет или он не читается.

    Нужен брифам: «Опора обложки» ссылается на залёт из этого списка. Полноту файла
    проверяет `check`, здесь только читаются поля «Видео».
    """
    path = run.path / FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    starts = [i for i, line in enumerate(lines) if _SECTION.match(line)]
    found: set[str] = set()
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        vid = (_fields(lines[start + 1: end]).get("Видео") or "").strip().strip("`")
        if vid:
            found.add(vid)
    return found


def check(run: runs.Run) -> tuple[str | None, list[str]]:
    """Основа разбора и список проблем (пустой — файл в порядке). Каждая называет файл и место."""
    path = run.path / FILE
    if not path.exists():
        return None, [f"`{FILE}`: файла нет в {run.path}. Агент ещё не записал разбор обложек"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, [f"`{FILE}`: файл не читается, нужен текст в кодировке UTF-8"]
    try:
        virals = _read_virals(run)
    except FileFormatError as err:
        return None, [str(err)]

    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if _SECTION.match(line)]
    top = lines[: starts[0]] if starts else lines
    head = _fields(top)
    problems: list[str] = []

    mode = (head.get("Основа разбора") or "").strip()
    if _empty(mode):
        problems.append(f"`{FILE}`, вверху файла: нет поля «Основа разбора»")
    elif mode not in MODES:
        problems.append(f"`{FILE}`, вверху файла: основа разбора «{mode}» не распознана. "
                        f"Допустимо: {', '.join(MODES)}")
    if not any(NOTE_GUESS in line for line in top if line.startswith(">")):
        problems.append(f"`{FILE}`, вверху файла: нет пометки «{NOTE_GUESS}, а не измерение»")
    if _empty(head.get("Запуск")):
        problems.append(f"`{FILE}`, вверху файла: нет поля «Запуск»")
    elif _placeholder(head["Запуск"]):
        problems.append(f"`{FILE}`, вверху файла: поле «Запуск» не заполнено (остался шаблонный текст)")
    if mode not in MODES:
        return None, problems

    if mode == MODE_NONE:
        reason = head.get("Причина")
        if _empty(reason):
            problems.append(f"`{FILE}`: основа «{MODE_NONE}», но нет строки «- Причина: …»")
        elif _placeholder(reason):
            problems.append(f"`{FILE}`: поле «Причина» не заполнено (остался шаблонный текст)")
        if starts:
            problems.append(f"`{FILE}`: основа «{MODE_NONE}», а блоки залётов есть; уберите их или "
                            "поменяйте основу")
        return mode, problems

    if mode == MODE_LINKS and not any(v.get("thumbnail_url") for v in virals):
        problems.append(f"`{FILE}`, вверху файла: основа «{MODE_LINKS}», а в `virals.json` ссылок на "
                        "обложки нет")
    if mode == MODE_FOLDER and not has_images(run):
        problems.append(f"`{FILE}`, вверху файла: основа «{MODE_FOLDER}», а в `{THUMBS_DIR}/` нет "
                        "картинок (jpg, png, webp)")

    by_id = {str(v["id"]): v for v in virals}
    seen: dict[str, str] = {}
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        # Блок кончается на ближайшем заголовке «##», в том числе итоговом.
        for i in range(start + 1, end):
            if _HEADING.match(lines[i]):
                end = i
                break
        m = _SECTION.match(lines[start])
        fields = _fields(lines[start + 1: end])
        vid = (fields.get("Видео") or "").strip()
        where = f"`{FILE}`, залёт {m[1]} «{m[2].strip()}»"
        if vid and vid in seen:
            problems.append(f"{where}: видео `{vid}` разобрано дважды")
        seen[vid] = where
        problems += _check_block(where, vid, fields, by_id)

    for vid in by_id:
        if vid not in seen:
            problems.append(f"`{FILE}`: нет разбора для залёта `{vid}`")

    headings = {m[1] for m in (_HEADING.match(line) for line in lines) if m}
    for name in SUMMARY_HEADINGS:
        body = _section_body(lines, name)
        if name not in headings:
            problems.append(f"`{FILE}`: нет раздела «{name}»")
        elif not body.strip():
            problems.append(f"`{FILE}`, раздел «{name}»: пустой")
        elif _placeholder(body):
            problems.append(f"`{FILE}`, раздел «{name}»: не заполнен (остался шаблонный текст)")
    return mode, problems


def _section_body(lines: list[str], name: str) -> str:
    body: list[str] = []
    inside = False
    for line in lines:
        m = _HEADING.match(line)
        if m:
            inside = m[1] == name
        elif inside:
            body.append(line)
    return "\n".join(body)


def _check_block(where: str, vid: str, fields: dict[str, str], by_id: dict) -> list[str]:
    problems = []
    for name in BLOCK_FIELDS:
        if name not in fields:
            problems.append(f"{where}: нет поля «{name}»")
        elif _empty(fields[name]):
            problems.append(f"{where}: поле «{name}» пустое")
        elif _placeholder(fields[name]):
            problems.append(f"{where}: поле «{name}» не заполнено (остался шаблонный текст)")
    if problems:
        return problems
    viral = by_id.get(vid)
    if viral is None:
        return [f"{where}: видео `{vid}` не залёт, в `virals.json` его нет"]
    stated = _number(fields["К норме канала"])
    real = viral.get("times_norm")
    if stated is None:
        problems.append(f"{where}: в поле «К норме канала» нужно число, а там «{fields['К норме канала']}»")
    elif real is not None and abs(stated - float(real)) > 0.01:
        problems.append(f"{where}: в поле «К норме канала» {stated:g}, а в `virals.json` {real:g}")
    return problems
