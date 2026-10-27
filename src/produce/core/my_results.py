"""Мои результаты: лучшие и слабые ролики моего канала по публичной статистике.

Считается только по кэшу запуска, одинаково для сбора и для импорта: видео моего канала
берутся из `cache/videos.json`. Закрытой аналитики (удержание, доходы) у скрипта нет.
"""

from statistics import median

from produce.core.collect import Cache

TOP = 3  # сколько лучших и сколько слабых показываем

NOT_SET = "Мой канал не задан, пропускаю"
NOT_FOUND_COLLECT = "Мой канал не найден на YouTube (проверьте `my_channel_id` в `settings.yaml`), пропускаю"
NOT_FOUND_IMPORT = "Моего канала нет в файле импорта, пропускаю"
NO_VIDEOS = "У моего канала нет роликов с открытой статистикой, пропускаю"


def _item(video: dict) -> dict:
    return {
        "id": video["id"],
        "title": video.get("title", ""),
        "url": f"https://www.youtube.com/watch?v={video['id']}",
        "published_at": video.get("published_at", ""),
        "views": int(video["views"]),
        "likes": video.get("likes"),
        "comments": video.get("comments"),
    }


def compute(cache: Cache, my_channel: str | None, source: str = "collect") -> dict:
    """Содержимое `my_results.json`: статус, пометка для человека и два списка роликов.

    Статусы: `not_set`, `not_found`, `no_videos`, `ok`. Трансляции и премьеры не считаются:
    их просмотры не сопоставимы с обычными роликами (как и в норме канала).
    """
    if not my_channel:
        return {"status": "not_set", "note": NOT_SET, "best": [], "weak": []}
    mine = [v for v in cache.videos.values()
            if v.get("channel_id") == my_channel and not v.get("is_live")
            and v.get("views") is not None]
    if my_channel not in cache.channels and not mine:
        note = NOT_FOUND_IMPORT if source == "import" else NOT_FOUND_COLLECT
        return {"status": "not_found", "channel_id": my_channel, "note": note, "best": [], "weak": []}
    if not mine:
        return {"status": "no_videos", "channel_id": my_channel, "note": NO_VIDEOS,
                "best": [], "weak": []}
    ordered = sorted(mine, key=lambda v: (-int(v["views"]), v["id"]))
    best_n = min(TOP, (len(ordered) + 1) // 2)
    weak_n = min(TOP, len(ordered) - best_n)
    best = ordered[:best_n]
    weak = list(reversed(ordered[len(ordered) - weak_n:])) if weak_n else []
    channel = cache.channels.get(my_channel, {})
    return {
        "status": "ok",
        "channel_id": my_channel,
        "channel_title": channel.get("title") or ordered[0].get("channel_title", ""),
        "videos": len(ordered),
        "median_views": round(median(int(v["views"]) for v in ordered)),
        "best": [_item(v) for v in best],
        "weak": [_item(v) for v in weak],
    }
