"""Оценка квоты и сбор данных: поиск, ролики конкурентов, последние ролики авторов.

Порядок шагов такой, чтобы любое место обрыва переживалось: каждый ответ YouTube
сразу пишется в кэш (`cache/videos.json`, `channels.json`, `progress.json`), а повторный
сбор пропускает всё, что уже лежит в кэше, и поэтому не тратит квоту заново.
"""

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from produce.core import quota, runs
from produce.core.errors import ProduceError, QuotaExceededError, RunError
from produce.core.files import read_json, write_json_atomic
from produce.core.settings import my_channel_id
from produce.core.youtube import (
    BATCH,
    COST_LIST,
    COST_SEARCH,
    SEARCH_PAGE_SIZE,
    PlaylistNotFound,
    YouTubeApi,
)

WINDOW_DAYS = 30
AUTHOR_UPLOADS = 20  # норма канала берётся по 10 без трансляций и премьер: берём с запасом
COMPETITOR_UPLOADS = 50
COMMENTS_UPPER = 20  # верхняя граница на комментарии залётов (до 20 видео по 1 ед.)


def now() -> datetime:
    """Текущее время. `PRODUCE_NOW` (ГГГГ-ММ-ДД) нужен автотестам: записанные ответы
    не стареют вместе с календарём."""
    fixed = os.environ.get("PRODUCE_NOW", "").strip()
    if fixed:
        return datetime.fromisoformat(fixed).replace(tzinfo=UTC)
    return datetime.now(UTC)


def _batches(ids: list[str]) -> list[list[str]]:
    return [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]


def _ceil_batches(n: int) -> int:
    return math.ceil(n / BATCH) if n > 0 else 0


class Cache:
    """Три файла в `cache/` запуска; каждая запись идёт через временный файл."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.videos: dict[str, dict] = self._load("videos.json", {})
        self.channels: dict[str, dict] = self._load("channels.json", {})
        self.progress: dict = self._load("progress.json", {})
        self.progress.setdefault("searches", {})
        self.progress.setdefault("unavailable_videos", [])
        self.progress.setdefault("unavailable_channels", [])

    def _load(self, name: str, default: dict) -> dict:
        path = self.dir / name
        if not path.exists():
            return default
        data = read_json(path)
        if not isinstance(data, dict):
            raise RunError(f"Файл {path} должен быть объектом")
        return data

    def save(self) -> None:
        write_json_atomic(self.dir / "videos.json", self.videos)
        write_json_atomic(self.dir / "channels.json", self.channels)
        write_json_atomic(self.dir / "progress.json", self.progress)


@dataclass
class Estimate:
    searches: int
    requests: int
    units: int  # сбор
    comment_units: int  # верхняя граница на комментарии залётов
    total: int


@dataclass
class Plan:
    """Что нужно собрать для сегмента: слова, регион, язык, конкуренты."""

    segment: str
    region: str
    language: str
    keywords: list[str]
    competitors: list[str]
    # Мой канал собирается как обычный автор (последние ролики): отсюда «Мои результаты».
    my_channel: str | None = None

    def search_key(self, query: str) -> str:
        return f"{self.region}|{self.language}|{query}"


def make_plan(settings: dict, segment: dict) -> Plan:
    seg_id = str(segment["id"])
    language = str(segment.get("language", "ru"))
    words = settings.get("keywords") or {}
    keywords = words.get(seg_id) or words.get(language) or []
    if not keywords:
        raise RunError(f"Для сегмента «{seg_id}» нет слов поиска в разделе keywords файла settings.yaml")
    comps = []
    for item in settings.get("competitors") or []:
        cid = item.get("id") if isinstance(item, dict) else item
        if cid:
            comps.append(str(cid))
    return Plan(seg_id, str(segment.get("region", "")), language,
                [str(k) for k in keywords], comps, my_channel_id(settings))


def estimate(plan: Plan, cache: Cache) -> Estimate:
    """Расход до первого запроса: известное считается точно, неизвестное — сверху.

    Неизвестные авторы ещё не найдены поиском, поэтому на каждый непройденный поиск
    закладывается полная страница авторов без пересечений.
    """
    searches = cache.progress["searches"]
    pending = [q for q in plan.keywords if plan.search_key(q) not in searches]
    found = [r for q in plan.keywords if plan.search_key(q) in searches
             for r in searches[plan.search_key(q)]]
    unknown = len(pending) * SEARCH_PAGE_SIZE

    known_videos = {r["id"] for r in found}
    skip = set(cache.videos) | set(cache.progress["unavailable_videos"])
    details_search = len(known_videos - skip) + unknown

    comps = set(plan.competitors)
    authors = {r["channel_id"] for r in found} | comps | ({plan.my_channel} if plan.my_channel else set())
    channels_missing = len({c for c in authors if c not in cache.channels
                            and c not in cache.progress["unavailable_channels"]}) + unknown
    need_recent = [c for c in authors if "recent_ids" not in cache.channels.get(c, {})
                   and c not in cache.progress["unavailable_channels"]]
    playlists = len(need_recent) + unknown
    recent_ids = sum(COMPETITOR_UPLOADS if c in comps else AUTHOR_UPLOADS for c in need_recent)
    recent_ids += unknown * AUTHOR_UPLOADS

    list_requests = (_ceil_batches(details_search) + _ceil_batches(channels_missing)
                     + playlists + _ceil_batches(recent_ids))
    units = len(pending) * COST_SEARCH + list_requests * COST_LIST
    return Estimate(len(pending), len(pending) + list_requests, units, COMMENTS_UPPER,
                    units + COMMENTS_UPPER)


@dataclass
class Summary:
    videos: int
    channels: int
    incomplete: int
    quota_spent: int
    requests: int


def summarize(run: runs.Run, cache: Cache) -> Summary:
    return Summary(len(cache.videos), len(cache.channels),
                   len(run.data.get("incomplete_data", [])),
                   int(run.data["quota_spent"]), int(run.data["requests_count"]))


def collect(run: runs.Run, plan: Plan, api: YouTubeApi, cache: Cache,
            progress: Callable[[str], None] = lambda text: None,
            moment: datetime | None = None) -> Summary:
    """Собирает всё, чего нет в кэше. Ошибки YouTube летят вызывающему, кэш уже сохранён."""
    moment = moment or now()
    since = moment - timedelta(days=WINDOW_DAYS)
    est = estimate(plan, cache)
    spent_before = int(run.data["quota_spent"])
    try:
        _collect(plan, api, cache, progress, since)
    except QuotaExceededError:
        _mark_incomplete(run, cache)
        done = int(run.data["quota_spent"]) - spent_before
        raise QuotaExceededError(quota.quota_message(done, est.units)) from None
    except ProduceError:
        # Сбой сети или отказ ключа: то, что уже пропущено, в run.json не теряется.
        _mark_incomplete(run, cache)
        raise
    _mark_incomplete(run, cache)
    return summarize(run, cache)


def _mark_incomplete(run: runs.Run, cache: Cache) -> None:
    """Пропущенные видео (недоступны, закрыты, без просмотров) -> `incomplete_data`."""
    unavailable = set(cache.progress["unavailable_videos"])
    empty = {vid for vid, v in cache.videos.items() if v.get("views") is None}
    runs.set_incomplete(run, sorted(unavailable | empty))


def _collect(plan: Plan, api: YouTubeApi, cache: Cache, progress: Callable[[str], None],
             since: datetime) -> None:
    searches = cache.progress["searches"]
    total = len(plan.keywords)
    for n, query in enumerate(plan.keywords, 1):
        key = plan.search_key(query)
        if key in searches:
            continue
        progress(f"поиск {n} из {total}")
        searches[key] = api.search(query, plan.region, plan.language, since)
        cache.save()

    found = [r for q in plan.keywords for r in searches[plan.search_key(q)]]
    progress("ролики из поиска")
    _fetch_videos(api, cache, sorted({r["id"] for r in found}))

    comps = set(plan.competitors)
    authors = sorted({r["channel_id"] for r in found} | comps
                     | ({plan.my_channel} if plan.my_channel else set()))
    progress("каналы")
    missing = [c for c in authors if c not in cache.channels
               and c not in cache.progress["unavailable_channels"]]
    for batch in _batches(missing):
        got = api.channels(batch)
        for ch in got:
            cache.channels[ch["id"]] = ch
        cache.progress["unavailable_channels"] += [c for c in batch
                                                   if c not in {g["id"] for g in got}]
        cache.save()
    for cid in comps:
        if cid in cache.channels:
            cache.channels[cid]["competitor"] = True
    cache.save()

    progress("последние ролики каналов")
    recent: list[str] = []
    for cid in authors:
        ch = cache.channels.get(cid)
        if ch is None:
            continue
        if "recent_ids" not in ch:
            _fetch_recent(api, cache, ch, cid in comps, since)
        recent += ch["recent_ids"]
    _fetch_videos(api, cache, sorted(set(recent)))


def _fetch_recent(api: YouTubeApi, cache: Cache, channel: dict, competitor: bool,
                  since: datetime) -> None:
    items: list[dict] = []
    if channel["video_count"] > 0 and channel["uploads_playlist"]:
        try:
            items = api.uploads(channel["uploads_playlist"],
                                COMPETITOR_UPLOADS if competitor else AUTHOR_UPLOADS)
        except PlaylistNotFound:
            items = []
    if competitor:
        # У конкурентов нужны ролики именно за период; у авторов — просто последние.
        items = [i for i in items if i["published_at"]
                 and datetime.fromisoformat(i["published_at"]) >= since]
    channel["recent_ids"] = [i["id"] for i in items]
    cache.save()


def _fetch_videos(api: YouTubeApi, cache: Cache, ids: list[str]) -> None:
    skip = set(cache.videos) | set(cache.progress["unavailable_videos"])
    for batch in _batches([i for i in ids if i not in skip]):
        got = api.videos(batch)
        for v in got:
            cache.videos[v["id"]] = v
        # Закрытые и удалённые видео YouTube не возвращает: помним, чтобы не спрашивать вновь.
        cache.progress["unavailable_videos"] += [i for i in batch
                                                 if i not in {g["id"] for g in got}]
        cache.save()
