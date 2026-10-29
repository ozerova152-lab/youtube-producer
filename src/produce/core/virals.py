"""Поиск залётов: видео, чьи просмотры и вовлечённость заметно выше нормы канала.

Считается только по кэшу запуска (сбор или импорт), без сети и ключа. Файл настроек
читается, но не меняется. Скорость набора просмотров пишется в запись залёта как
дополнительный сигнал и на отбор не влияет.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from produce.core import runs
from produce.core.collect import WINDOW_DAYS, Cache, now
from produce.core.errors import RunError
from produce.core.files import write_json_atomic

DEFAULTS = {
    "views_multiplier": 3,
    "likes_ratio": 0.02,
    "comments_ratio": 0.001,
    "norm_videos": 10,
    "min_channel_videos": 5,
}
NEAREST = 5
SECONDS_PER_DAY = 86400
LOW_DATA = "мало данных"


@dataclass
class Thresholds:
    views_multiplier: float
    likes_ratio: float
    comments_ratio: float
    norm_videos: int
    min_channel_videos: int


def thresholds_from(settings: dict) -> Thresholds:
    raw = {**DEFAULTS, **{k: v for k, v in (settings.get("thresholds") or {}).items()
                          if k in DEFAULTS and v is not None}}
    try:
        return Thresholds(float(raw["views_multiplier"]), float(raw["likes_ratio"]),
                          float(raw["comments_ratio"]), int(raw["norm_videos"]),
                          int(raw["min_channel_videos"]))
    except (TypeError, ValueError):
        raise RunError("В разделе thresholds файла settings.yaml должны быть числа. "
                       "Файл не изменён") from None


def _published(video: dict) -> datetime | None:
    text = str(video.get("published_at") or "")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=now().tzinfo)


def channel_norm(videos: dict[str, dict], channel_id: str, exclude_id: str,
                 th: Thresholds) -> tuple[float | None, int, int]:
    """Норма канала: медиана просмотров последних `norm_videos` обычных роликов без проверяемого.

    Трансляции, премьеры и ролики без счётчика просмотров не считаются.
    Возвращает (норма или None, размер выборки, сколько обычных роликов у канала); None, если их меньше минимума.
    """
    regular = [v for v in videos.values()
               if v.get("channel_id") == channel_id and not v.get("is_live")
               and v.get("views") is not None]
    pool = [v for v in regular if v["id"] != exclude_id]
    pool.sort(key=lambda v: _published(v) or datetime.min.replace(tzinfo=now().tzinfo),
              reverse=True)
    sample = pool[:th.norm_videos]
    # «Мало данных» считается по всем обычным роликам канала, включая проверяемое:
    # у канала ровно с 5 роликами норма есть (по 4 остальным).
    if len(regular) < th.min_channel_videos or not sample:
        return None, len(sample), len(regular)
    return float(median(v["views"] for v in sample)), len(sample), len(regular)


def _ratio(part: int | None, whole: int) -> float | None:
    if part is None or whole <= 0:
        return None
    return part / whole


def _record(video: dict, norm: float, sample: int, th: Thresholds, moment: datetime) -> dict:
    views = int(video["views"])
    likes_r = _ratio(video.get("likes"), views)
    comments_r = _ratio(video.get("comments"), views)
    published = _published(video)
    days = max((moment - published).total_seconds() / SECONDS_PER_DAY, 1.0) if published else 1.0
    times = views / norm if norm > 0 else None
    # Доли порога в долях единицы: ближайшие к порогу — те, у кого слабейшее условие сильнее.
    parts = [
        min(times / th.views_multiplier, 1.0) if times is not None else 0.0,
        min(likes_r / th.likes_ratio, 1.0) if likes_r is not None and th.likes_ratio else 0.0,
        min(comments_r / th.comments_ratio, 1.0)
        if comments_r is not None and th.comments_ratio else 0.0,
    ]
    passed = (times is not None and times >= th.views_multiplier
              and likes_r is not None and likes_r >= th.likes_ratio
              and comments_r is not None and comments_r >= th.comments_ratio)
    return {
        "id": video["id"],
        "title": video.get("title", ""),
        "channel_id": video.get("channel_id", ""),
        "channel_title": video.get("channel_title", ""),
        "url": f"https://www.youtube.com/watch?v={video['id']}",
        "published_at": video.get("published_at", ""),
        "duration_seconds": video.get("duration_seconds"),
        "views": views,
        "norm": round(norm),
        "norm_sample": sample,
        "times_norm": round(times, 2) if times is not None else None,
        "likes": video.get("likes"),
        "likes_ratio": round(likes_r, 4) if likes_r is not None else None,
        "comments": video.get("comments"),
        "comments_ratio": round(comments_r, 4) if comments_r is not None else None,
        "views_per_day": round(views / days),
        "_closeness": min(parts),
        "_passed": passed,
    }


def find(cache: Cache, th: Thresholds, moment: datetime | None = None) -> dict:
    """Возвращает содержимое `virals.json`; ничего не пишет."""
    moment = moment or now()
    since = moment - timedelta(days=WINDOW_DAYS)
    virals, others, skipped = [], [], []
    for video in cache.videos.values():
        published = _published(video)
        if video.get("views") is None or video.get("is_live"):
            continue
        # Старые ролики авторов лежат в кэше ради нормы, залётами они не бывают.
        if published is None or published < since:
            continue
        norm, sample, count = channel_norm(cache.videos, video.get("channel_id", ""), video["id"], th)
        if norm is None:
            skipped.append({"id": video["id"], "title": video.get("title", ""),
                            "channel_id": video.get("channel_id", ""), "reason": LOW_DATA,
                            "channel_videos": count})
            continue
        rec = _record(video, norm, sample, th, moment)
        (virals if rec["_passed"] else others).append(rec)

    virals.sort(key=lambda r: (-(r["times_norm"] or 0), r["id"]))
    others.sort(key=lambda r: (-r["_closeness"], r["id"]))
    nearest = [] if virals else others[:NEAREST]
    for rec in virals + others:
        rec.pop("_passed")
        rec["closeness"] = round(rec.pop("_closeness"), 3)
    skipped.sort(key=lambda s: s["id"])
    return {
        "generated_at": moment.isoformat(timespec="seconds"),
        "thresholds": {"views_multiplier": th.views_multiplier, "likes_ratio": th.likes_ratio,
                       "comments_ratio": th.comments_ratio, "norm_videos": th.norm_videos,
                       "min_channel_videos": th.min_channel_videos},
        "checked": len(virals) + len(others),
        "virals": virals,
        "nearest": nearest,
        "skipped": skipped,
    }


def find_and_save(run: runs.Run, settings: dict) -> dict:
    cache = Cache(run.path / "cache")
    if not cache.videos:
        raise RunError("Данных ещё нет: сначала `produce collect` или `produce import`")
    result = find(cache, thresholds_from(settings))
    write_json_atomic(run.path / "virals.json", result)
    runs.advance_stage(run, "залёты")
    return result


def times_text(rec: dict) -> str:
    """«×12.68» или «норма 0», если у канала нулевая медиана и кратность не определена."""
    return f"×{rec['times_norm']:g}" if rec["times_norm"] is not None else "норма 0"
