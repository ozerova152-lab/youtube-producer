"""Проверка брифов `briefs/<номер>.md`: структура по шаблону, не смысл.

Один бриф — один файл, вид и статус в шапке. Скрипт сверяет бриф с `virals.json`: образцы
и залёт-основа существуют, ссылки настоящие; поля вида заполнены; язык значений совпадает
с `brief_lang` запуска; статус при создании пустой (его ставит человек, не агент).
Качество идей проверяет человек. Вид «длинное видео» — T11; Shorts и посты добавит T12.
"""

import re

from produce.core import runs
from produce.core.errors import FileFormatError
from produce.core.files import read_json
from produce.core.niche import _fields, _placeholders, _split

BRIEFS_DIR = "briefs"
KIND_LONG = "длинное видео"
KINDS = (KIND_LONG,)
STATUSES = ("принят", "отклонён", "позже")
STAGE_DECISION = "брифы на решение"

HEADER = ["Запуск", "Вид", "Язык брифа"]
LONG_SECTIONS = {
    "Идея и основа": ["Идея", "Залёт", "Чем отличаемся"],
    "Начало и длина": ["Первые 15 секунд", "Длина"],
    "Упаковка": ["Название 1", "Название 2", "Описание триггерное", "Описание SEO",
                 "Хэштеги", "Теги", "Идея обложки"],
    "Главные эмоции": ["Эмоции"],
}
MIN_STRUCTURE_LINES = 3
EDIT_MARK = "монтаж"
TITLE_LIMIT = 100  # длина названия на YouTube
# Поля, текст которых должен быть на языке брифа (названия полей остаются русскими).
LANG_FIELDS = ["Идея", "Первые 15 секунд", "Название 1", "Описание триггерное", "Описание SEO"]
CYRILLIC_LANGS = {"ru", "uk", "be", "bg", "kk", "sr", "mk", "ky", "mn"}
LATIN_LANGS = {"en", "de", "fr", "es", "pt", "it", "pl", "tr", "nl", "cs", "ro", "id"}

_FILE = re.compile(r"^(\d+)\.md$")
_TITLE = re.compile(r"^#\s+Бриф\s+(\d+)\s*:\s*(.*)$")
_STATUS_LINE = re.compile(r"^-\s+Статус\s*:\s*(.*)$")
_SAMPLE = re.compile(r"^-\s+`?([^:\s`]+)`?\s*:\s*(\S+)")


class Brief:
    """Разобранный файл брифа: номер, название, вид и статус из шапки."""

    def __init__(self, number: int, title: str, kind: str, status: str, name: str):
        self.number, self.title, self.kind, self.status, self.name = number, title, kind, status, name


def _script_ratio(text: str, letters: str) -> float:
    found = [c for c in text if c.isalpha()]
    if not found:
        return 1.0
    return sum(1 for c in found if re.match(letters, c)) / len(found)


def _language_problems(where: str, language: str, fields: dict[str, str]) -> list[str]:
    if language in CYRILLIC_LANGS:
        pattern, script = r"[а-яёіїєґ]", "кириллицей"
    elif language in LATIN_LANGS:
        pattern, script = r"[a-zÀ-ſ]", "латиницей"
    else:
        return []  # язык вне списка: письмо не определить, смысл смотрит человек
    problems = []
    for name in LANG_FIELDS:
        value = fields.get(name, "")
        if value and not _placeholders_in(value) and _script_ratio(value.lower(), pattern) < 0.5:
            problems.append(f"{where}: поле «{name}» не на языке брифа «{language}» "
                            f"(ожидается текст {script})")
    return problems


def _load_virals(run: runs.Run) -> dict[str, dict]:
    path = run.path / "virals.json"
    if not path.exists():
        raise FileFormatError("Залётов ещё нет: сначала `produce virals`")
    data = read_json(path)
    items = data.get("virals", []) if isinstance(data, dict) else []
    return {str(v["id"]): v for v in items}


def _check_samples(where: str, lines: list[str], virals: dict[str, dict],
                   base: str | None) -> list[str]:
    rows = [line for line in lines if line.startswith("-")]
    wanted = min(2, len(virals))
    if not (wanted <= len(rows) <= 3):
        return [(f"{where}: в разделе «Образцы» {len(rows)}, нужно {wanted}–3 образца "
                 "строками «- id: ссылка — чем полезен»")]
    problems, seen = [], []
    for row in rows:
        m = _SAMPLE.match(row)
        if not m:
            problems.append(f"{where}: образец «{row}» не разобран, нужна строка «- id: ссылка — чем полезен»")
            continue
        vid, url = m[1], m[2].rstrip(".,;")
        seen.append(vid)
        if vid not in virals:
            problems.append(f"{where}: образец `{vid}` не залёт, в `virals.json` его нет")
        elif url != virals[vid].get("url"):
            problems.append(f"{where}: у образца `{vid}` ссылка «{url}» не совпадает с `virals.json`")
    if base and base in virals and base not in seen:
        problems.append(f"{where}: залёт-основа `{base}` не назван среди образцов")
    if len(set(seen)) != len(seen):
        problems.append(f"{where}: образцы повторяются")
    return problems


def _check_long(where: str, sections: dict[str, list[str]], run_language: str,
                virals: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    fields: dict[str, str] = {}
    for title, required in LONG_SECTIONS.items():
        if title not in sections:
            problems.append(f"{where}: нет раздела «{title}»")
            continue
        section_fields = _fields(sections[title])
        fields.update(section_fields)
        problems += _placeholders("", "", section_fields, required)
    # Префикс «`имя`, место» ставится ниже: _placeholders пишет «`…`, …: сообщение».
    problems = [re.sub(r"^``, : ", f"{where}: ", p) for p in problems]

    structure = sections.get("Структура")
    if structure is None:
        problems.append(f"{where}: нет раздела «Структура»")
    else:
        items = [line for line in structure if line.startswith("-")]
        if len(items) < MIN_STRUCTURE_LINES:
            problems.append(f"{where}: в разделе «Структура» {len(items)} "
                            f"{'строка' if len(items) == 1 else 'строк'}, нужно не меньше {MIN_STRUCTURE_LINES}")
        elif not any(EDIT_MARK in line.lower() for line in items):
            problems.append(f"{where}: в разделе «Структура» нет пометок по монтажу "
                            f"(слово «{EDIT_MARK}» в строке)")
        if any(_placeholders_in(line) for line in items):
            problems.append(f"{where}: раздел «Структура» не заполнен (остался шаблонный текст)")

    for name in ("Название 1", "Название 2", "Название 3"):
        if len(fields.get(name, "")) > TITLE_LIMIT:
            problems.append(f"{where}: «{name}» длиннее {TITLE_LIMIT} знаков")
    if "Название 3" in fields and _placeholders_in(fields["Название 3"]):
        problems.append(f"{where}: поле «Название 3» не заполнено (остался шаблонный текст); "
                        "если третьего названия нет, удалите строку")
    tags = fields.get("Хэштеги", "")
    if tags and not _placeholders_in(tags) and not all(t.startswith("#") for t in tags.split()):
        problems.append(f"{where}: в поле «Хэштеги» каждый хэштег начинается с «#»")
    length = fields.get("Длина", "")
    if length and not _placeholders_in(length) and not re.search(r"\d", length):
        problems.append(f"{where}: в поле «Длина» нужно число, а там «{length}»")

    base = fields.get("Залёт", "").strip("` ") or None
    if base and not _placeholders_in(base) and base not in virals:
        problems.append(f"{where}: залёт `{base}` не найден в `virals.json`")
    problems += _check_samples(where, sections.get("Образцы", []), virals, base) \
        if "Образцы" in sections else [f"{where}: нет раздела «Образцы»"]
    problems += _language_problems(where, run_language, fields)
    return problems


def _placeholders_in(text: str) -> bool:
    return bool(re.search(r"<[^>]+>", text))


def check_file(run: runs.Run, path_name: str, virals: dict[str, dict], decision_open: bool
               ) -> tuple[Brief | None, list[str]]:
    """Проблемы одного брифа и его шапка (None, если шапка не читается)."""
    rel = f"{BRIEFS_DIR}/{path_name}"
    path = run.path / BRIEFS_DIR / path_name
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None, [f"`{rel}`: файл не читается, нужен текст в кодировке UTF-8"]
    file_number = int(_FILE.match(path_name)[1])
    where = f"`{rel}`"

    head, blocks = _split(lines, "##")
    title_match = next((m for m in map(_TITLE.match, head) if m), None)
    if not title_match:
        return None, [f"{where}: нет заголовка «# Бриф {file_number}: <название>»"]
    problems: list[str] = []
    if int(title_match[1]) != file_number:
        problems.append(f"{where}: в заголовке номер {title_match[1]}, а файл {path_name}")
    title = title_match[2].strip()
    if not title or _placeholders_in(title):
        problems.append(f"{where}: в заголовке нет названия брифа")

    head_fields = _fields(head)
    problems += [re.sub(r"^``, : ", f"{where}, шапка: ", p)
                 for p in _placeholders("", "", head_fields, HEADER)]
    status_line = next((m for m in map(_STATUS_LINE.match, head) if m), None)
    if not status_line:
        problems.append(f"{where}, шапка: нет строки «- Статус:» (при создании она пустая)")
        status = ""
    else:
        status = status_line[1].strip()
        if status and status not in STATUSES:
            problems.append(f"{where}, шапка: статус «{status}» не распознан. Допустимо "
                            f"«{'», «'.join(STATUSES)}» или пусто")
        elif status and decision_open:
            problems.append(f"{where}, шапка: статус «{status}» стоит до остановки на решение. "
                            "Статус ставит человек, при создании он пустой")

    kind = head_fields.get("Вид", "").strip()
    language = head_fields.get("Язык брифа", "").strip()
    run_language = str(run.data.get("brief_lang", "ru"))
    if language and language != run_language:
        problems.append(f"{where}, шапка: язык брифа «{language}», а в запуске `--brief-lang` "
                        f"«{run_language}»")
    if kind and kind not in KINDS:
        problems.append(f"{where}, шапка: вид «{kind}» не распознан. Допустимо: {', '.join(KINDS)}")
    elif kind == KIND_LONG:
        problems += _check_long(where, dict(blocks), run_language, virals)
    return Brief(file_number, title, kind, status, path_name), problems


def check(run: runs.Run) -> tuple[list[Brief], list[str]]:
    """Брифы запуска и проблемы всех файлов (пустой список проблем — всё в порядке)."""
    folder = run.path / BRIEFS_DIR
    names = sorted(p.name for p in folder.glob("*.md")) if folder.is_dir() else []
    if not names:
        return [], [f"`{BRIEFS_DIR}/`: брифов нет в {run.path}. Агент ещё не записал их"]
    try:
        virals = _load_virals(run)
    except FileFormatError as err:
        return [], [str(err)]
    decision_open = runs.STAGES.index(run.stage) < runs.STAGES.index(STAGE_DECISION)
    found: list[Brief] = []
    problems: list[str] = []
    for name in names:
        if not _FILE.match(name):
            problems.append(f"`{BRIEFS_DIR}/{name}`: имя файла должно быть вида 01.md")
            continue
        brief, file_problems = check_file(run, name, virals, decision_open)
        problems += file_problems
        if brief:
            found.append(brief)
    return found, problems
