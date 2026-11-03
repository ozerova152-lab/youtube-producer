"""Обзор запуска `00-overview.md`: вход в папку запуска для новичка.

Файл производный: строится только из состояния папки запуска и `run.json`, без сети и ключа,
и пересоздаётся целиком. Время сборки в него не пишется, поэтому повторная пересборка без
изменений даёт тот же текст байт в байт. В обзор попадают статусы, имена файлов, даты и числа:
ни ключа, ни текстов комментариев, ни названий видео, ни путей вне папки запуска.
"""

import json
from pathlib import Path

from produce.core import quota, runs
from produce.core.errors import ProduceError
from produce.core.files import write_text_atomic

FILE = "00-overview.md"
DONE = "✅"
TODO = "⏳ ещё не сделано"
SKIPPED = "⏭ пропущено: залётов нет"
UNKNOWN_DATE = "дата неизвестна"
NOT_YET = "ещё не было"

# (номер, название, файл или папка, «что это и зачем»): тексты из экрана «Обзор запуска»
# в `docs/spec/04-user-flows.md`.
_VIRALS = ("1", "Залётные ролики", "report.md",
           ("видео вашей ниши, набравшие просмотров заметно больше обычного для канала; "
           "с них начинается всё остальное"))
_ANALYSIS = ("2", "Разбор", "analysis.md",
             "о чём пишут зрители под залётами и почему они взлетели")
_COVERS = ("2б", "Обложки", "covers.md",
           "что общего у обложек залётов; описание — предположение агента")
_NICHE = ("3", "Ниша", "niche.md", "какие темы и форматы повторяются среди залётов")
_COMPETITORS = ("4", "Конкуренты", "candidates.md",
                "каналы, за которыми стоит следить; в настройки их добавляете вы")
_STRATEGY = ("5", "Стратегия", "strategy.md",
             "что снимать и как часто; решение за вами, пока статус «черновик»")
_BRIEFS = ("6", "Брифы и сценарии", "briefs/",
           "по файлу на каждое видео, сценарий и упаковка; вы ставите «принят», «отклонён» или «позже»")
_PLAN = ("7", "План", "plan.md", "месячный план из принятых брифов")

_NEXT = {
    "настроен": "собрать данные: агент покажет расход квоты и дождётся вашего «да»",
    "оценка квоты": "ответить «да» на оценку квоты, тогда пойдёт сбор данных",
    "собрано": "найти залёты и посмотреть ваши результаты",
    "залёты": "разобрать причины по комментариям",
    "разбор готов": "собрать нишу и кандидатов в конкуренты (обложки можно разобрать по желанию)",
    "ниша готова": "составить стратегию; она придёт черновиком",
    "стратегия ждёт утверждения": "прочитать `strategy.md` и, если согласны, заменить статус на "
                                  "«утверждена»; потом сказать «готово»",
    "стратегия утверждена": "сделать брифы по стратегии",
    "брифы на решение": "поставить брифам статусы «принят», «отклонён» или «позже»; из принятых "
                        "соберётся план",
    "план готов": "месяц готов, публикацию делаете вы; новая версия или следующий месяц — "
                  "по вашей просьбе",
}


def _brief_files(run: runs.Run) -> list[str]:
    """Имена файлов брифов вида `01.md` (по возрастанию номера); остальное в обзор не идёт."""
    folder = run.path / "briefs"
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir()
                  if p.is_file() and p.suffix == ".md" and p.stem.isdigit())


def _no_virals(run: runs.Run) -> bool:
    """`virals.json` читается и залётов в нём нет: разбор причин пропускают."""
    try:
        data = json.loads((run.path / "virals.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and not data.get("virals")


def _spent(value: object) -> str:
    """Расход квоты числом; нечисловое и отрицательное значение не выдумывается."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return "нет данных"
    return f"{int(value):,} из {quota.DAILY_LIMIT:,}".replace(",", " ")


def _plain(value: object) -> str:
    """Короткое значение поля run.json для шапки; странное заменяется прочерком."""
    ok = isinstance(value, (str, int)) and not isinstance(value, bool)
    text = str(value).strip() if ok else ""
    return text if text and len(text) <= 40 and "\n" not in text else "—"


def _date(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _dates(run: runs.Run) -> tuple[str, str]:
    started = _date(run.data.get("started_on")) or UNKNOWN_DATE
    collected = _date(run.data.get("collected_on"))
    if collected is None:
        reached = runs.STAGES.index(run.stage) >= runs.STAGES.index("собрано")
        collected = UNKNOWN_DATE if reached else NOT_YET
    return started, collected


def _line(item: tuple[str, str, str, str], status: str, exists: bool) -> str:
    number, title, name, why = item
    target = f"[`{name}`]({name})" if exists else f"`{name}`"
    return f"{number}. {title} {status} — {target}: {why}"


def build(run: runs.Run, channel_name: str | None = None) -> str:
    """Текст обзора по текущему состоянию папки запуска."""
    data = run.data
    started, collected = _dates(run)
    lines = [
        f"# Обзор запуска {run.path.name}",
        "",
        (f"Канал: {channel_name or run.path.parent.parent.name}, сегмент {_plain(data.get('segment'))}, "
         f"версия {_plain(data.get('version'))}, этап: {run.stage}."),
        f"Запуск начат: {started}.",
        f"Последний сбор данных: {collected}.",
        f"Расход квоты: {_spent(data.get('quota_spent'))}.",
        "",
        ("> Файл создаёт скрипт и обновляет после каждого шага, не правьте его. "
         "Пересобрать: `produce overview`."),
        "",
    ]
    steps: list[tuple[tuple[str, str, str, str], str, bool]] = []
    steps.append((_VIRALS, "", (run.path / _VIRALS[2]).is_file()))
    analysis_exists = (run.path / _ANALYSIS[2]).is_file()
    steps.append((_ANALYSIS, "skip" if not analysis_exists and _no_virals(run) else "",
                  analysis_exists))
    if (run.path / _COVERS[2]).is_file():
        steps.append((_COVERS, "", True))
    for item in (_NICHE, _COMPETITORS, _STRATEGY):
        steps.append((item, "", (run.path / item[2]).is_file()))
    briefs = _brief_files(run)
    steps.append((_BRIEFS, "", bool(briefs)))
    steps.append((_PLAN, "", (run.path / _PLAN[2]).is_file()))

    for item, mark, exists in steps:
        status = DONE if exists else (SKIPPED if mark == "skip" else TODO)
        if item is _BRIEFS and exists:
            lines.append(f"{item[0]}. {item[1]} {status} — `briefs/`: {item[3]}")
            lines += [f"   - [`briefs/{name}`](briefs/{name})" for name in briefs]
        else:
            lines.append(_line(item, status, exists))
    lines += [
        "",
        "Служебные файлы: `run.json`, `cache/`, открывать их необязательно.",
        f"Что дальше: {_NEXT.get(run.stage, 'продолжить по сценарию месяца')}.",
        "",
    ]
    return "\n".join(lines)


def write(run: runs.Run, channel_name: str | None = None) -> Path:
    """Пересобирает `00-overview.md` из состояния папки; возвращает путь к файлу."""
    try:
        fresh = runs.load_run(run.path)  # run.json мог измениться после того, как объект создан
    except ProduceError:
        fresh = run
    path = run.path / FILE
    write_text_atomic(path, build(fresh, channel_name))
    return path
