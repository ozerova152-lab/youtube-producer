"""Комментарии залётов: оценка квоты и докачка (`cache/comments.json`).

Качаются только залёты из `virals.json`, до `max_comments` самых популярных у каждого.
Каждое видео пишется в файл сразу, поэтому обрыв (сбой сети, квота) ничего не теряет, а
повтор берёт только недокачанное и не тратит квоту заново. Закрытые комментарии — пустой
список: «уже спрашивали». Тексты комментариев — чужие данные: в логи и сообщения не идут.
"""

from collections.abc import Callable
from pathlib import Path

from produce.core import runs
from produce.core.errors import RunError
from produce.core.files import read_json, write_json_atomic
from produce.core.youtube import COST_LIST, CommentsUnavailable, YouTubeApi

MAX_COMMENTS = 100  # предел YouTube на один запрос и потолок из слоя 1
MIN_COMMENTS = 10


def comments_path(run: runs.Run) -> Path:
    return run.path / "cache" / "comments.json"


def load(run: runs.Run) -> dict[str, list[dict]]:
    """{id видео: [{text, likes}]}; файла нет — пустой словарь."""
    path = comments_path(run)
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise RunError(f"Файл {path} должен быть объектом")
    return data


def limits_from(settings: dict) -> tuple[int, int]:
    """(сколько комментариев брать, сколько нужно для эмоций) из `thresholds`."""
    section = settings.get("thresholds") or {}
    try:
        top = int(section.get("max_comments", MAX_COMMENTS))
        low = int(section.get("min_comments", MIN_COMMENTS))
    except (TypeError, ValueError):
        raise RunError("В разделе thresholds файла settings.yaml должны быть числа. "
                       "Файл не изменён") from None
    return max(1, min(top, MAX_COMMENTS)), max(low, 0)


def viral_ids(run: runs.Run) -> list[str]:
    path = run.path / "virals.json"
    if not path.exists():
        raise RunError("Залётов ещё нет: сначала `produce virals`")
    data = read_json(path)
    if not isinstance(data, dict):
        raise RunError(f"Файл {path} должен быть объектом")
    return [str(v["id"]) for v in data.get("virals", [])]


def pending(run: runs.Run, ids: list[str]) -> list[str]:
    have = load(run)
    return [i for i in ids if i not in have]


def estimate_units(count: int) -> int:
    """По одному запросу на залёт, один запрос — 1 единица."""
    return count * COST_LIST


def fetch(run: runs.Run, api: YouTubeApi, ids: list[str], limit: int,
          progress: Callable[[str], None] = lambda text: None) -> dict[str, list[dict]]:
    """Докачивает комментарии `ids`; пишет файл после каждого видео."""
    have = load(run)
    todo = [i for i in ids if i not in have]
    for n, vid in enumerate(todo, 1):
        progress(f"комментарии {n} из {len(todo)}")
        try:
            have[vid] = api.comments(vid, limit)
        except CommentsUnavailable:
            have[vid] = []
        write_json_atomic(comments_path(run), have)
    if any(have.get(i) for i in ids):
        run.data["no_comments"] = False
        write_json_atomic(run.path / "run.json", run.data)
    return have
