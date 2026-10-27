"""Импорт видео и каналов из файла CSV/JSON: запасной путь без ключа YouTube.

Файл сначала целиком читается и проверяется в памяти, и только потом пишется кэш:
при ошибке формата кэш запуска остаётся как был. Формат описан в `docs/import-format.md`.
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from produce.core import runs
from produce.core.collect import AUTHOR_UPLOADS, Cache
from produce.core.errors import FileFormatError
from produce.core.files import write_json_atomic

MIN_CHANNEL_VIDEOS = 5

VIDEO_REQUIRED = ["id", "title", "channel_id", "published_at", "views"]
VIDEO_OPTIONAL = ["description", "channel_title", "duration_seconds", "is_live", "likes", "comments"]
CSV_CHANNEL_COLUMNS = ["channel_subscribers"]
CHANNEL_REQUIRED = ["id", "title", "subscribers"]
COMMENT_REQUIRED = ["video_id", "text"]

_TRUE = {"true", "1", "да", "yes"}
_FALSE = {"false", "0", "нет", "no", ""}


@dataclass
class Imported:
    videos: dict[str, dict]
    channels: dict[str, dict]
    comments: dict[str, list[dict]] = field(default_factory=dict)
    skipped_channels: list[str] = field(default_factory=list)


def _bad(where: str, name: str, value: object, expected: str) -> FileFormatError:
    return FileFormatError(
        f"{where}: в {('колонке' if where.startswith('Строка') else 'поле')} `{name}` "
        f"значение «{value}» не подходит ({expected}). Исправьте и повторите импорт"
    )


def _int(value: object, where: str, name: str, required: bool) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise _bad(where, name, "", "нужно целое число")
        return None
    try:
        number = int(str(value).strip().replace(" ", ""))
    except ValueError:
        raise _bad(where, name, value, "нужно целое число") from None
    if number < 0:
        raise _bad(where, name, value, "число не может быть отрицательным")
    return number


def _date(value: object, where: str) -> str:
    text = str(value or "").strip()
    try:
        datetime.fromisoformat(text)
    except ValueError:
        raise _bad(where, "published_at", text, "нужна дата вида 2026-10-20T10:00:00Z") from None
    return text


def _bool(value: object, where: str, name: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise _bad(where, name, value, "нужно да или нет")


def _text(row: dict, name: str, where: str, required: bool) -> str:
    value = row.get(name)
    if value is None or not str(value).strip():
        if required:
            raise FileFormatError(
                f"{where}: пустое значение в {('колонке' if where.startswith('Строка') else 'поле')} "
                f"`{name}`. Заполните его и повторите импорт"
            )
        return ""
    return str(value)


def _video(row: dict, where: str) -> dict:
    duration = _int(row.get("duration_seconds"), where, "duration_seconds", False)
    return {
        "id": _text(row, "id", where, True).strip(),
        "title": _text(row, "title", where, True),
        "description": _text(row, "description", where, False),
        "channel_id": _text(row, "channel_id", where, True).strip(),
        "channel_title": _text(row, "channel_title", where, False),
        "published_at": _date(row.get("published_at"), where),
        "duration_seconds": duration,
        "is_live": _bool(row.get("is_live"), where, "is_live"),
        "views": _int(row.get("views"), where, "views", True),
        "likes": _int(row.get("likes"), where, "likes", False),
        "comments": _int(row.get("comments"), where, "comments", False),
    }


def _read_csv(path: Path) -> tuple[list[dict], list[dict]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise FileFormatError(f"Не найден файл: {path}") from None
    except (OSError, UnicodeDecodeError):
        raise FileFormatError(f"Не удалось прочитать файл {path}: нужен текст в кодировке UTF-8") from None
    reader = csv.DictReader(text.splitlines())
    header = [h.strip() for h in (reader.fieldnames or [])]
    if len(header) == 1 and ";" in header[0]:
        raise FileFormatError("В файле CSV разделитель «;», а нужна запятая. Замените и повторите импорт")
    for name in VIDEO_REQUIRED + CSV_CHANNEL_COLUMNS:
        if name not in header:
            raise FileFormatError(f"В файле нет колонки `{name}`. Добавьте её и повторите импорт")
    videos, channels = [], {}
    for n, raw in enumerate(reader, start=2):
        row = {(k or "").strip(): v for k, v in raw.items()}
        where = f"Строка {n}"
        videos.append({"_where": where, **row})
        cid = (row.get("channel_id") or "").strip()
        if cid and cid not in channels:
            subs = _int(row.get("channel_subscribers"), where, "channel_subscribers", False)
            channels[cid] = {"id": cid, "title": row.get("channel_title") or "", "subscribers": subs}
    return videos, list(channels.values())


def _read_json(path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise FileFormatError(f"Не найден файл: {path}") from None
    except (OSError, UnicodeDecodeError):
        raise FileFormatError(f"Не удалось прочитать файл {path}: нужен текст в кодировке UTF-8") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise FileFormatError(
            f"Файл {path} повреждён: ошибка формата JSON в строке {err.lineno}, столбце {err.colno}. "
            "Исправьте и повторите импорт"
        ) from err
    if not isinstance(data, dict):
        raise FileFormatError("В файле JSON должен быть объект с полями `videos` и `channels`")
    parts = []
    for key in ("videos", "channels"):
        if not isinstance(data.get(key), list):
            raise FileFormatError(f"В файле нет поля `{key}` (список). Добавьте его и повторите импорт")
        parts.append(data[key])
    comments = data.get("comments", [])
    if not isinstance(comments, list):
        raise FileFormatError("Поле `comments` должно быть списком")
    return parts[0], parts[1], comments


def _check_keys(items: list, kind: str, required: list[str]) -> None:
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise FileFormatError(f"{kind} №{n}: нужен объект с полями, а не «{item}»")
        for name in required:
            if name not in item:
                raise FileFormatError(
                    f"{kind} №{n}: нет поля `{name}`. Добавьте его и повторите импорт")


def parse(path: Path, min_channel_videos: int = MIN_CHANNEL_VIDEOS) -> Imported:
    """Читает и проверяет файл; ничего не пишет на диск."""
    suffix = path.suffix.lower()
    comment_items: list[dict] = []
    if suffix == ".csv":
        raw_videos, raw_channels = _read_csv(path)
    elif suffix == ".json":
        raw_videos, raw_channels, comment_items = _read_json(path)
        _check_keys(raw_videos, "Видео", VIDEO_REQUIRED)
        _check_keys(raw_channels, "Канал", CHANNEL_REQUIRED)
        _check_keys(comment_items, "Комментарий", COMMENT_REQUIRED)
        for n, v in enumerate(raw_videos, 1):
            v["_where"] = f"Видео №{n}"
    else:
        raise FileFormatError("Нужен файл CSV или JSON (расширение .csv или .json)")

    videos: dict[str, dict] = {}
    for raw in raw_videos:
        where = raw.pop("_where")
        video = _video(raw, where)
        if video["id"] in videos:
            raise FileFormatError(f"{where}: видео `{video['id']}` встречается дважды. Оставьте одну запись")
        videos[video["id"]] = video

    channels: dict[str, dict] = {}
    for n, raw in enumerate(raw_channels, 1):
        where = f"Канал №{n}"
        cid = _text(raw, "id", where, True).strip()
        if cid in channels:
            raise FileFormatError(f"{where}: канал `{cid}` встречается дважды. Оставьте одну запись")
        channels[cid] = {
            "id": cid,
            "title": _text(raw, "title", where, False),
            "subscribers": _int(raw.get("subscribers"), where, "subscribers", False),
        }

    for vid, video in videos.items():
        if video["channel_id"] not in channels:
            raise FileFormatError(
                f"Видео `{vid}`: канала `{video['channel_id']}` нет в списке каналов. "
                "Добавьте канал и повторите импорт")

    comments: dict[str, list[dict]] = {}
    for n, c in enumerate(comment_items, 1):
        where = f"Комментарий №{n}"
        vid = _text(c, "video_id", where, True).strip()
        if vid not in videos:
            raise FileFormatError(f"{where}: видео `{vid}` нет в списке видео")
        likes = _int(c.get("likes"), where, "likes", False)
        comments.setdefault(vid, []).append({"text": _text(c, "text", where, True), "likes": likes})

    return _finish(videos, channels, comments, min_channel_videos)


def _finish(videos: dict, channels: dict, comments: dict, min_videos: int) -> Imported:
    """Недавние ролики канала = его видео из файла (кроме трансляций); мало роликов — канал пропущен."""
    by_channel: dict[str, list[dict]] = {cid: [] for cid in channels}
    for v in videos.values():
        by_channel[v["channel_id"]].append(v)
    skipped = []
    for cid in list(channels):
        regular = sorted((v for v in by_channel[cid] if not v["is_live"]),
                         key=lambda v: v["published_at"], reverse=True)
        if len(regular) < min_videos:
            skipped.append(cid)
            for v in by_channel[cid]:
                videos.pop(v["id"])
                comments.pop(v["id"], None)
            del channels[cid]
            continue
        ch = channels[cid]
        ch["video_count"] = len(by_channel[cid])
        ch["uploads_playlist"] = ""
        ch["recent_ids"] = [v["id"] for v in regular[:AUTHOR_UPLOADS]]
    return Imported(videos, channels, comments, skipped)


def import_file(run: runs.Run, path: Path, min_channel_videos: int = MIN_CHANNEL_VIDEOS) -> Imported:
    """Проверяет файл и кладёт данные в кэш запуска в формате сбора."""
    result = parse(path, min_channel_videos)
    cache = Cache(run.path / "cache")
    cache.videos.update(result.videos)
    cache.channels.update(result.channels)
    cache.save()
    comments_path = run.path / "cache" / "comments.json"
    if result.comments:
        write_json_atomic(comments_path, result.comments)
    run.data["source"] = "import"
    run.data["no_comments"] = not result.comments
    runs.advance_stage(run, "собрано")
    write_json_atomic(run.path / "run.json", run.data)
    return result
