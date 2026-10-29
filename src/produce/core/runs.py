"""Запуски: папка `runs/<ГГГГ-ММ>_<сегмент>_v<N>/` и `run.json` в ней."""

import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from produce.core import quota
from produce.core.errors import RunError
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


def current_month(today: date | None = None) -> str:
    return (today or date.today()).strftime("%Y-%m")


def load_run(path: Path) -> Run:
    data = read_json(path / "run.json")
    if not isinstance(data, dict):
        raise RunError(f"Файл {path / 'run.json'} должен быть объектом")
    check_stage(data.get("stage", ""))
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
