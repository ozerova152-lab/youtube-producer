"""Клиент YouTube Data API v3 (официальный клиент Google).

Единственное место, где программа ходит в сеть. Ключ живёт только внутри клиента:
в сообщения ошибок он не попадает (текст исключений Google содержит адрес запроса
с ключом, поэтому наружу выходят только свои фразы).
"""

import json
import logging
import re
import time
from collections.abc import Callable
from datetime import datetime

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from produce.core.errors import KeyRejectedError, NetworkError, QuotaExceededError

COST_SEARCH = 100
COST_LIST = 1
SEARCH_PAGE_SIZE = 25
BATCH = 50  # предел id в одном запросе videos/channels

_KEY_REASONS = {
    "keyInvalid", "API_KEY_INVALID", "ipRefererBlocked", "accessNotConfigured",
    "API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED",
}
_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}
_RATE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}  # временный отказ, не дневная квота
RETRIES = 3  # повторов после первой неудачи
BACKOFF = (1, 2, 4)  # пауза в секундах перед 1-м, 2-м и 3-м повтором: растёт
GIVE_UP = (
    "YouTube не отвечает: 3 попытки подряд. Собранное сохранено. "
    "Запустите позже, повторно квота не потратится; «да» понадобится снова"
)
_DURATION = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


class _HideKey(logging.Filter):
    """Клиент Google пишет адрес запроса (с ключом) в свой лог на уровне INFO."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self._key = key

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        if self._key in text:
            record.msg, record.args = text.replace(self._key, "***"), None
        return True


def pause(seconds: float) -> None:
    """Пауза между повторами. Отдельной функцией, чтобы автотесты её подменяли."""
    time.sleep(seconds)


class _Transient(Exception):
    """Внутренний сигнал: сбой, который имеет смысл повторить."""


class PlaylistNotFound(Exception):
    """У канала нет списка загрузок (пустой канал)."""


def parse_duration(iso: str | None) -> int | None:
    """`PT1H2M3S` -> секунды; прямые трансляции без длины -> None."""
    m = _DURATION.match(iso or "")
    if not m or not any(m.groups()):
        return None
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def _reasons(err: HttpError) -> tuple[set[str], str]:
    try:
        body = json.loads(err.content.decode("utf-8", "replace"))["error"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return set(), ""
    found = {e.get("reason", "") for e in body.get("errors", []) if isinstance(e, dict)}
    found |= {d.get("reason", "") for d in body.get("details", []) if isinstance(d, dict)}
    return found, str(body.get("message", ""))


class YouTubeApi:
    """Тонкая обёртка: четыре метода YouTube и перевод ошибок в свои.

    `on_request(cost)` вызывается после каждого успешного обращения: так считается
    квота и счётчик обращений в `run.json`.
    """

    def __init__(self, key: str, on_request: Callable[[int], None] | None = None,
                 http: httplib2.Http | None = None) -> None:
        for name in ("googleapiclient.discovery", "googleapiclient.http"):
            logging.getLogger(name).addFilter(_HideKey(key))
        self._svc = build("youtube", "v3", developerKey=key, cache_discovery=False,
                          static_discovery=True, http=http)
        self._on_request = on_request or (lambda cost: None)

    def _run(self, request, cost: int) -> dict:
        """Один запрос с повторами при сбоях YouTube; ключ и квота повторов не получают."""
        for attempt in range(RETRIES + 1):
            try:
                response = self._once(request, cost)
            except _Transient:
                if attempt == RETRIES:
                    raise NetworkError(GIVE_UP) from None
                logging.getLogger(__name__).info("сбой YouTube, повтор %d из %d", attempt + 1, RETRIES)
                pause(BACKOFF[attempt])
                continue
            self._on_request(cost)
            return response
        raise AssertionError("недостижимо")  # pragma: no cover

    def _once(self, request, cost: int) -> dict:
        try:
            return request.execute()
        except HttpError as err:
            reasons, message = _reasons(err)
            status = err.resp.status
            if reasons & _KEY_REASONS or "API key not valid" in message:
                raise KeyRejectedError(
                    "Ключ не подошёл (YouTube отклонил). Сбор остановлен. "
                    "Проверьте ключ в `.env` или загрузите файл"
                ) from None
            if reasons & _QUOTA_REASONS:
                raise QuotaExceededError("Квота на сегодня закончилась.") from None
            if status == 404 and "playlistNotFound" in reasons:
                self._on_request(cost)
                raise PlaylistNotFound() from None
            if status >= 500 or status == 429 or reasons & _RATE_REASONS:
                raise _Transient() from None
            # Остальные отказы (400, 403, 404) повтором не лечатся.
            raise NetworkError(
                "YouTube ответил отказом на запрос. Собранное сохранено. "
                "Запустите позже, повторно квота не потратится; «да» понадобится снова"
            ) from None
        except (OSError, httplib2.HttpLib2Error):
            raise _Transient() from None

    def search(self, query: str, region: str, language: str,
               published_after: datetime) -> list[dict]:
        """Видео по словам за период, самые просматриваемые первыми (100 ед.)."""
        req = self._svc.search().list(
            part="snippet", q=query, type="video", order="viewCount",
            regionCode=region, relevanceLanguage=language,
            publishedAfter=published_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
            maxResults=SEARCH_PAGE_SIZE,
        )
        items = self._run(req, COST_SEARCH).get("items", [])
        return [
            {"id": i["id"]["videoId"], "channel_id": i["snippet"]["channelId"]}
            for i in items if i.get("id", {}).get("videoId")
        ]

    def videos(self, ids: list[str]) -> list[dict]:
        """Подробности и статистика видео (1 ед. на пачку до 50)."""
        req = self._svc.videos().list(
            part="snippet,contentDetails,statistics,liveStreamingDetails",
            id=",".join(ids),
        )
        return [_video(i) for i in self._run(req, COST_LIST).get("items", [])]

    def channels(self, ids: list[str]) -> list[dict]:
        """Каналы: название, подписчики, число роликов, список загрузок (1 ед.)."""
        req = self._svc.channels().list(part="snippet,statistics,contentDetails",
                                        id=",".join(ids))
        return [_channel(i) for i in self._run(req, COST_LIST).get("items", [])]

    def uploads(self, playlist_id: str, limit: int) -> list[dict]:
        """Последние загрузки канала через список загрузок, а не поиском (1 ед.)."""
        req = self._svc.playlistItems().list(part="contentDetails", playlistId=playlist_id,
                                             maxResults=limit)
        return [
            {"id": i["contentDetails"]["videoId"],
             "published_at": i["contentDetails"].get("videoPublishedAt", "")}
            for i in self._run(req, COST_LIST).get("items", [])
        ]


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _video(item: dict) -> dict:
    snip, stats = item.get("snippet", {}), item.get("statistics", {})
    duration = item.get("contentDetails", {}).get("duration")
    return {
        "id": item["id"],
        "title": snip.get("title", ""),
        "description": snip.get("description", ""),
        "channel_id": snip.get("channelId", ""),
        "channel_title": snip.get("channelTitle", ""),
        "published_at": snip.get("publishedAt", ""),
        "duration_seconds": parse_duration(duration),
        # Трансляции и премьеры в норму канала не идут (слой 1): помечаем здесь.
        "is_live": "liveStreamingDetails" in item
        or snip.get("liveBroadcastContent", "none") != "none",
        "views": _int(stats.get("viewCount")),
        "likes": _int(stats.get("likeCount")),
        "comments": _int(stats.get("commentCount")),
    }


def _channel(item: dict) -> dict:
    stats = item.get("statistics", {})
    hidden = stats.get("hiddenSubscriberCount", False)
    return {
        "id": item["id"],
        "title": item.get("snippet", {}).get("title", ""),
        "subscribers": None if hidden else _int(stats.get("subscriberCount")),
        "video_count": _int(stats.get("videoCount")) or 0,
        "uploads_playlist": item.get("contentDetails", {}).get("relatedPlaylists", {})
        .get("uploads", ""),
    }
