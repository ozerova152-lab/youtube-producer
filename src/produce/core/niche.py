"""Проверка `niche.md` и `candidates.md`: структура по шаблонам, не смысл.

Скрипт сверяет файлы с `virals.json`: форматы (длинные от 3 минут / Shorts) посчитаны
правильно, повторяющиеся каналы названы все и только настоящие, у каждого кандидата есть
причина, а канал не из `settings.yaml` (конкурент уже записан или это мой канал).
Качество выводов проверяет человек.
"""

import re

from produce.core import runs
from produce.core.errors import FileFormatError
from produce.core.files import read_json

NICHE = "niche.md"
CANDIDATES = "candidates.md"
LONG_SECONDS = 180  # от 3 минут — длинное видео, короче — Shorts
NOTE_NO_VIRALS = "Залётов нет"
NO_REPEATS = "Повторяющихся каналов нет"
NO_CANDIDATES = "Повторяющихся каналов нет, кандидатов не предлагаю"
SETTINGS_UNTOUCHED = "`settings.yaml` не менял"
FORMAT_LONG = "Длинные (от 3 минут)"
FORMAT_SHORTS = "Shorts (до 3 минут)"
FORMAT_UNKNOWN = "Длительность неизвестна"

_FIELD = re.compile(r"^-\s+([^:]+?)\s*:\s*(.*)$")
_PLACEHOLDER = re.compile(r"<[^>]+>")
_COUNT = re.compile(r"^(\d+)\s*(?:\((.*)\))?$")


def _fields(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines:
        m = _FIELD.match(line)
        if m:
            found[m[1]] = m[2].strip()
    return found


def _ids(text: str) -> list[str]:
    return [p.strip().strip("`") for p in re.split(r"[,;]", text) if p.strip().strip("`")]


def _read(run: runs.Run, name: str) -> tuple[list[str] | None, list[str]]:
    path = run.path / name
    if not path.exists():
        return None, [f"`{name}`: файла нет в {run.path}. Агент ещё не записал его"]
    try:
        return path.read_text(encoding="utf-8").splitlines(), []
    except (OSError, UnicodeDecodeError):
        return None, [f"`{name}`: файл не читается, нужен текст в кодировке UTF-8"]


def load_virals(run: runs.Run) -> list[dict]:
    path = run.path / "virals.json"
    if not path.exists():
        raise FileFormatError("Залётов ещё нет: сначала `produce virals`")
    data = read_json(path)
    return list(data.get("virals", [])) if isinstance(data, dict) else []


def format_of(viral: dict) -> str:
    seconds = viral.get("duration_seconds")
    if not isinstance(seconds, (int, float)):
        return FORMAT_UNKNOWN
    return FORMAT_LONG if seconds >= LONG_SECONDS else FORMAT_SHORTS


def repeating_channels(virals: list[dict]) -> dict[str, list[str]]:
    """Канал -> id его залётов; повторяющимся считается канал с двумя и больше залётами."""
    by_channel: dict[str, list[str]] = {}
    for v in virals:
        by_channel.setdefault(str(v.get("channel_id", "")), []).append(str(v["id"]))
    return {c: ids for c, ids in by_channel.items() if c and len(ids) >= 2}


def candidate_channels(repeating: dict[str, list[str]], known: set[str]) -> dict[str, list[str]]:
    """Повторяющиеся каналы, которых нет среди конкурентов и это не мой канал."""
    return {c: ids for c, ids in repeating.items() if c not in known}


def _split(lines: list[str], level: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Делит текст на шапку и блоки по заголовкам уровня `##` или `###`."""
    prefix = level + " "
    head: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith(prefix):
            blocks.append((line[len(prefix):].strip(), []))
        elif blocks:
            blocks[-1][1].append(line)
        else:
            head.append(line)
    return head, blocks


def _placeholders(name: str, where: str, fields: dict[str, str], required: list[str]) -> list[str]:
    problems = []
    for field in required:
        value = fields.get(field)
        if value is None:
            problems.append(f"`{name}`, {where}: нет поля «{field}»")
        elif not value.strip():
            problems.append(f"`{name}`, {where}: поле «{field}» пустое")
        elif _PLACEHOLDER.search(value):
            problems.append(f"`{name}`, {where}: поле «{field}» не заполнено (остался шаблонный текст)")
    return problems


def check_niche(run: runs.Run, virals: list[dict]) -> list[str]:
    """Проблемы `niche.md` (пустой список — файл в порядке)."""
    lines, problems = _read(run, NICHE)
    if lines is None:
        return problems
    head, sections = _split(lines, "##")
    head_fields = _fields(head)
    problems += _placeholders(NICHE, "вверху файла", head_fields, ["Запуск", "Залётов в основе"])
    stated = head_fields.get("Залётов в основе", "").strip()
    if stated.isdigit() and int(stated) != len(virals):
        problems.append(f"`{NICHE}`, вверху файла: «Залётов в основе» {stated}, "
                        f"а в `virals.json` {len(virals)}")
    elif stated and not stated.isdigit() and not _PLACEHOLDER.search(stated):
        problems.append(f"`{NICHE}`, вверху файла: в поле «Залётов в основе» нужно число, а там «{stated}»")

    note = any(line.lstrip("> ").startswith(NOTE_NO_VIRALS) for line in head)
    if not virals:
        if not note:
            problems.append(f"`{NICHE}`, вверху файла: залётов нет, но нет пометки «{NOTE_NO_VIRALS}»")
        return problems
    if note:
        problems.append(f"`{NICHE}`, вверху файла: пометка «{NOTE_NO_VIRALS}» стоит, а залёты в `virals.json` есть")

    by_name = {title: body for title, body in sections}
    for title in ("Темы", "Форматы", "Повторяющиеся каналы"):
        if title not in by_name:
            problems.append(f"`{NICHE}`: нет раздела «{title}»")
    ids = {str(v["id"]) for v in virals}
    if "Темы" in by_name:
        problems += _check_themes(by_name["Темы"], ids)
    if "Форматы" in by_name:
        problems += _check_formats(by_name["Форматы"], virals)
    if "Повторяющиеся каналы" in by_name:
        problems += _check_repeats(by_name["Повторяющиеся каналы"], repeating_channels(virals))
    return problems


def _check_themes(body: list[str], viral_ids: set[str]) -> list[str]:
    _, blocks = _split(body, "###")
    if not blocks:
        return [f"`{NICHE}`, раздел «Темы»: нет ни одной темы"]
    problems: list[str] = []
    covered: set[str] = set()
    for title, lines in blocks:
        where = f"тема «{title}»"
        fields = _fields(lines)
        problems += _placeholders(NICHE, where, fields, ["Залёты", "Что объединяет"])
        for vid in _ids(fields.get("Залёты", "")):
            if vid not in viral_ids:
                problems.append(f"`{NICHE}`, {where}: видео `{vid}` не залёт, в `virals.json` его нет")
            covered.add(vid)
    for vid in sorted(viral_ids - covered):
        problems.append(f"`{NICHE}`, раздел «Темы»: залёт `{vid}` не отнесён ни к одной теме")
    return problems


def _check_formats(body: list[str], virals: list[dict]) -> list[str]:
    fields = _fields(body)
    expected: dict[str, list[str]] = {FORMAT_LONG: [], FORMAT_SHORTS: [], FORMAT_UNKNOWN: []}
    for v in virals:
        expected[format_of(v)].append(str(v["id"]))
    problems: list[str] = []
    for name, real in expected.items():
        value = fields.get(name)
        if value is None:
            problems.append(f"`{NICHE}`, раздел «Форматы»: нет поля «{name}»")
            continue
        m = _COUNT.match(value.strip())
        if not m:
            problems.append(f"`{NICHE}`, раздел «Форматы»: в поле «{name}» нужно число и в скобках видео, "
                            f"а там «{value}»")
            continue
        if int(m[1]) != len(real):
            problems.append(f"`{NICHE}`, раздел «Форматы»: в поле «{name}» {m[1]}, "
                            f"а по длительности из `virals.json` {len(real)}")
        elif set(_ids(m[2] or "")) != set(real):
            problems.append(f"`{NICHE}`, раздел «Форматы»: в поле «{name}» названы не те видео "
                            f"(по `virals.json`: {', '.join(real) or 'нет'})")
    return problems


def _check_repeats(body: list[str], repeating: dict[str, list[str]]) -> list[str]:
    _, blocks = _split(body, "###")
    text = "\n".join(body)
    if not repeating:
        if blocks:
            return [(f"`{NICHE}`, раздел «Повторяющиеся каналы»: у канала меньше двух залётов, "
                     "повторяющимся он не считается")]
        if NO_REPEATS not in text:
            return [(f"`{NICHE}`, раздел «Повторяющиеся каналы»: каналов с двумя и больше залётами нет, "
                     f"нужна строка «{NO_REPEATS}»")]
        return []
    problems: list[str] = []
    named: set[str] = set()
    for title, lines in blocks:
        where = f"канал «{title}»"
        fields = _fields(lines)
        problems += _placeholders(NICHE, where, fields, ["Канал", "Залёты", "Что повторяется"])
        cid = fields.get("Канал", "").strip().strip("`")
        if cid in repeating:
            named.add(cid)
            if set(_ids(fields.get("Залёты", ""))) != set(repeating[cid]):
                problems.append(f"`{NICHE}`, {where}: залёты названы не те "
                                f"(по `virals.json`: {', '.join(repeating[cid])})")
        elif cid and not _PLACEHOLDER.search(cid):
            problems.append(f"`{NICHE}`, {where}: у канала `{cid}` меньше двух залётов, "
                            "повторяющимся он не считается")
    for cid, ids in repeating.items():
        if cid not in named:
            problems.append(f"`{NICHE}`, раздел «Повторяющиеся каналы»: не назван канал `{cid}` "
                            f"(залётов: {len(ids)})")
    return problems


def check_candidates(run: runs.Run, virals: list[dict], known: set[str]) -> list[str]:
    """Проблемы `candidates.md`. `known` — конкуренты из настроек и мой канал."""
    lines, problems = _read(run, CANDIDATES)
    if lines is None:
        return problems
    head, blocks = _split(lines, "##")
    text = "\n".join(lines)
    problems += _placeholders(CANDIDATES, "вверху файла", _fields(head), ["Запуск"])
    if SETTINGS_UNTOUCHED not in text:
        problems.append(f"`{CANDIDATES}`, вверху файла: нет строки «{SETTINGS_UNTOUCHED}»")
    eligible = candidate_channels(repeating_channels(virals), known)
    if not eligible and not blocks and NO_CANDIDATES not in text:
        return problems + [f"`{CANDIDATES}`: нужна строка «{NO_CANDIDATES}.»"]
    named: set[str] = set()
    for title, body in blocks:
        where = f"кандидат «{title.split(':', 1)[-1].strip()}»"
        fields = _fields(body)
        problems += _placeholders(CANDIDATES, where, fields, ["Канал", "Залёты", "Причина"])
        cid = fields.get("Канал", "").strip().strip("`")
        if cid in known:
            problems.append(f"`{CANDIDATES}`, {where}: канал `{cid}` уже в `settings.yaml` "
                            "(конкурент или мой канал), предлагать его не нужно")
        elif cid in eligible:
            if cid in named:
                problems.append(f"`{CANDIDATES}`, {where}: канал `{cid}` назван дважды")
            named.add(cid)
        elif cid and not _PLACEHOLDER.search(cid):
            problems.append(f"`{CANDIDATES}`, {where}: канал `{cid}` не повторяется в залётах "
                            "(меньше двух), кандидатом он быть не может")
    for cid in eligible:
        if cid not in named:
            problems.append(f"`{CANDIDATES}`: не назван канал `{cid}` — повторяется в залётах, "
                            "нужен кандидат с причиной")
    return problems
