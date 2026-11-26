"""Запуски: папка `runs/<ГГГГ-ММ>_<сегмент>_v<N>/` и `run.json` в ней."""

import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from produce.core import quota
from produce.core.clock import now
from produce.core.errors import FileFormatError, RunError
from produce.core.files import read_json, write_json_atomic

# Порядок важен: по нему определяется «дошёл ли запуск до конца».
STAGES = [
    "настроен",
    "оценка квоты",
    "собрано",
    "залёты",
    "разбор готов",
    "ниша готова",
    "стратегия ждёт утверждения",
    "стратегия утверждена",
    "брифы на решение",
    "план готов",
]
FINAL_STAGE = "план готов"
MAX_VERSION = 999  # номер версии запуска внутри месяца

_NAME = re.compile(r"^(?P<month>\d{4}-\d{2})_(?P<segment>.+)_v(?P<version>\d+)$")


@dataclass
class Run:
    path: Path
    data: dict

    @property
    def stage(self) -> str:
        return self.data["stage"]

    @property
    def finished(self) -> bool:
        return self.stage == FINAL_STAGE


@dataclass
class StartResult:
    run: Run
    action: str  # "created" | "new_version" | "resume" | "ask_new_version"


def check_stage(stage: str) -> str:
    if stage not in STAGES:
        raise RunError(f"Неизвестный этап «{stage}». Допустимые: {', '.join(STAGES)}")
    return stage


def runs_dir(channel_dir: Path) -> Path:
    return channel_dir / "runs"


def today() -> date:
    """Сегодняшний день по часам проекта (учитывает `PRODUCE_NOW`)."""
    return now().date()


def current_month(day: date | None = None) -> str:
    return (day or today()).strftime("%Y-%m")


def _check_version(path: Path, data: dict) -> None:
    """`version` правят руками, и он нужен всем командам (сравнение запусков, новая версия, отчёт).

    Поэтому проверяем один раз при чтении запуска, а не `int()` в каждом месте: иначе нечисловое
    значение падает трейсбеком в `later`, `start` и других. Число в кавычках, дробное, `true`, ноль
    и отрицательное тоже ошибка: при ручной правке это почти всегда опечатка. Значение из файла в
    сообщение не копируем.
    """
    value = data.get("version")
    match = _NAME.match(path.name)
    hint = (f"впишите номер из названия папки (здесь v{match['version']}, значит {int(match['version'])})"
            if match else "впишите целое число")
    where = f"В файле `runs/{path.name}/run.json`"
    if not (isinstance(value, int) and not isinstance(value, bool) and value >= 1):
        raise RunError(
            f"{where} поле `version` должно быть целым числом, например 1. "
            f"Скорее всего, файл правили руками. Откройте его, {hint} и запустите команду снова. "
            "Старые запуски не изменены"
        )
    if value > MAX_VERSION:
        # 10**30 породил бы папку с абсурдным номером; больше тысячи запусков за месяц не бывает
        raise RunError(
            f"{where} поле `version` слишком большое: допустимо целое число от 1 до {MAX_VERSION}. "
            f"Скорее всего, файл правили руками. Откройте его, {hint} и запустите команду снова. "
            "Старые запуски не изменены"
        )
    if match and value != int(match["version"]):
        raise RunError(
            f"{where} в поле `version` стоит число, не совпадающее с номером в названии папки "
            f"(v{match['version']}). Впишите {int(match['version'])} и запустите команду снова. "
            "Папку не переименовывайте. Старые запуски не изменены"
        )


def _broken_run_message(path: Path, cause: BaseException | None = None) -> str:
    """Один человечный текст на все виды испорченного `run.json`: пустой, оборванный, не объект, нет файла.

    Показываем только относительный путь и место ошибки (строка и столбец: слой 2 требует «название файла
    и места»). Содержимое файла, текст разбора и абсолютный путь не показываем. Предлагаем переименовать папку,
    а не удалять: в кэше лежит собранное за квоту, а переименованная папка просто перестаёт быть запуском.
    """
    line, column = getattr(cause, "lineno", None), getattr(cause, "colno", None)
    place = f" (ошибка формата в строке {line}, столбце {column})" if line and column else ""
    return (
        f"Файл `runs/{path.name}/run.json` пуст или повреждён{place}. Остальные файлы запуска не тронуты. "
        "Что делать: если у вас есть копия этого файла, верните её. Если нет, переименуйте папку запуска "
        "(например, допишите `-old` в конце: она перестанет считаться запуском, но ничего не удалится) "
        "и запустите `produce start`: создастся новый запуск. Кэш сбора из старой папки можно скопировать "
        "в новую, чтобы не тратить квоту заново"
    )


def load_run(path: Path) -> Run:
    try:
        data = read_json(path / "run.json")
    except FileFormatError as err:
        raise RunError(_broken_run_message(path, err.__cause__)) from err
    if not isinstance(data, dict):
        raise RunError(_broken_run_message(path))
    check_stage(data.get("stage", ""))
    _check_version(path, data)
    return Run(path, data)


def list_runs(channel_dir: Path, month: str, segment: str) -> list[Run]:
    """Запуски месяца и сегмента по возрастанию версии. Сегменты не смешиваются."""
    base = runs_dir(channel_dir)
    found: list[tuple[int, Path]] = []
    if base.is_dir():
        for child in base.iterdir():
            m = _NAME.match(child.name)
            if m and m["month"] == month and m["segment"] == segment and child.is_dir():
                found.append((int(m["version"]), child))
    return [load_run(p) for _, p in sorted(found)]


def segment_run_dirs(channel_dir: Path, segment: str) -> list[tuple[str, int, Path]]:
    """Все папки запусков сегмента по возрастанию (месяц, версия); другие сегменты не попадают.

    Читает только имена папок: история не зависит от того, читается ли `run.json` старых запусков.
    """
    base = runs_dir(channel_dir)
    found: list[tuple[str, int, Path]] = []
    if base.is_dir():
        for child in base.iterdir():
            m = _NAME.match(child.name)
            if m and m["segment"] == segment and child.is_dir():
                found.append((m["month"], int(m["version"]), child))
    return sorted(found)


def _create(channel_dir: Path, month: str, segment: str, brief_lang: str, version: int,
            copy_cache_from: Run | None) -> Run:
    path = runs_dir(channel_dir) / f"{month}_{segment}_v{version}"
    path.mkdir(parents=True)
    if copy_cache_from and (copy_cache_from.path / "cache").is_dir():
        shutil.copytree(copy_cache_from.path / "cache", path / "cache")
    else:
        (path / "cache").mkdir()
    data = {
        "month": month,
        "segment": segment,
        "brief_lang": brief_lang,
        "version": version,
        "stage": STAGES[0],
        "quota_spent": 0,
        "requests_count": 0,
        "awaiting_confirmation": False,
        "incomplete_data": [],
        "started_on": today().isoformat(),
    }
    write_json_atomic(path / "run.json", data)
    return Run(path, data)


def start_run(channel_dir: Path, month: str, segment: str, brief_lang: str,
              force_new_version: bool = False) -> StartResult:
    """Находит или создаёт запуск месяца и сегмента.

    Новая версия создаётся только по прямой просьбе (`force_new_version`). На запуске
    «план готов» без неё ничего не пишется и возвращается "ask_new_version": вопрос
    человеку задаёт интерфейс. Незавершённый запуск возвращается с его этапом.
    """
    existing = list_runs(channel_dir, month, segment)
    if not existing:
        return StartResult(_create(channel_dir, month, segment, brief_lang, 1, None), "created")
    last = existing[-1]
    if not force_new_version:
        return StartResult(last, "ask_new_version" if last.finished else "resume")
    if last.data["version"] >= MAX_VERSION:
        raise RunError(
            "Достигнут предел: 999 версий запуска за месяц и сегмент. "
            "Дождитесь следующего месяца. Старые запуски не изменены"
        )
    new = _create(channel_dir, month, segment, brief_lang, last.data["version"] + 1, last)
    return StartResult(new, "new_version")


def set_stage(run: Run, stage: str) -> None:
    run.data["stage"] = check_stage(stage)
    write_json_atomic(run.path / "run.json", run.data)


def record_usage(run: Run, units: int, requests: int, ledger: Path,
                 day: date | None = None) -> int:
    """Пишет расход в run.json и в общий дневной учёт; возвращает сумму за сутки."""
    total = quota.add_spent(ledger, units, day)
    run.data["quota_spent"] += units
    run.data["requests_count"] += requests
    write_json_atomic(run.path / "run.json", run.data)
    return total


def mark_collected(run: Run) -> None:
    """Дата последнего успешного сбора или импорта: для обзора запуска."""
    run.data["collected_on"] = today().isoformat()
    write_json_atomic(run.path / "run.json", run.data)


def set_awaiting(run: Run, awaiting: bool) -> None:
    """Отметка «ожидает подтверждения»: оценка квоты показана, слова человека ещё нет."""
    run.data["awaiting_confirmation"] = awaiting
    write_json_atomic(run.path / "run.json", run.data)


def set_incomplete(run: Run, ids: list[str]) -> None:
    run.data["incomplete_data"] = ids
    write_json_atomic(run.path / "run.json", run.data)


def advance_stage(run: Run, stage: str) -> None:
    """Двигает этап только вперёд: повторный сбор не откатывает уже пройденное."""
    if STAGES.index(check_stage(stage)) > STAGES.index(run.stage):
        set_stage(run, stage)
