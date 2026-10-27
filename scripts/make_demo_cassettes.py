"""Собирает демо-кассеты `examples/demo/cassettes/` вручную, без обращений к YouTube.

Пока нет ключа, настоящих записей нет. Скрипт строит выдуманный «мир» (каналы и ролики
демо-канала) и отвечает на запросы клиента Google ответами в форме официальных ответов
YouTube Data API v3; обмен записывается в формат pytest-recording (vcrpy). Ключ в
кассеты не попадает: параметры `key` и `publishedAfter` вырезаются.
Когда ключ появится, кассеты заменяются настоящими записями (`pytest --record-mode=once`).

Запуск: `.venv/bin/python scripts/make_demo_cassettes.py`
"""

import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

import httplib2
import yaml

from produce.core.youtube import YouTubeApi

OUT = Path(__file__).parent.parent / "examples" / "demo" / "cassettes"
RECORDED = date(2026, 10, 27).isoformat()
STRIP = {"key", "publishedAfter"}


def _video(vid, channel, title, published, views, likes=1, comments=1, live=False,
           duration="PT8M30S"):
    return {"id": vid, "channel": channel, "title": title, "published": published,
            "views": views, "likes": likes, "comments": comments, "live": live,
            "duration": duration}


def _ru_world():
    channels = {
        "UC_demo_a": ("Нейро для всех", 48000, False),
        "UC_demo_b": ("ИИ с нуля", 12000, False),
        "UC_demo_c": ("Мини-канал", 800, True),  # скрытые подписчики и всего 3 ролика
        "UC_demo_d": ("Промпт-лаб", 150000, False),
        "UC_demo_comp": ("AI Daily", 90000, False),
    }
    v = [
        _video("demoVid_a01", "UC_demo_a", "Как я заменил ассистента нейросетью за вечер", "2026-10-12T10:00:00Z", 90000, 5400, 610),
        _video("demoVid_a02", "UC_demo_a", "ChatGPT для отчётов: 5 приёмов", "2026-10-03T10:00:00Z", 6200, 210, 40),
        _video("demoVid_a03", "UC_demo_a", "Нейросеть против Excel", "2026-09-20T10:00:00Z", 5100, 180, 22),
        _video("demoVid_a04", "UC_demo_a", "Промпты для писем", "2026-09-05T10:00:00Z", 4800, 150, 18),
        _video("demoVid_a05", "UC_demo_a", "Шпаргалка по ChatGPT", "2026-08-25T10:00:00Z", 5300, 190, 25, duration="PT45S"),
        _video("demoVid_a06", "UC_demo_a", "Обзор новых моделей", "2026-08-10T10:00:00Z", 4500, 120, 12),
        _video("demoVid_b01", "UC_demo_b", "ИИ для новичков: с чего начать", "2026-10-08T12:00:00Z", 2500, 60, 4),
        _video("demoVid_b02", "UC_demo_b", "Нейросети для работы без кода", "2026-10-15T12:00:00Z", 1900, 41, 3),
        _video("demoVid_b03", "UC_demo_b", "Что умеет нейросеть сегодня", "2026-09-12T12:00:00Z", 2100, 50, 6),
        _video("demoVid_b04", "UC_demo_b", "Мой набор ИИ-инструментов", "2026-08-30T12:00:00Z", 1700, 30, 5),
        _video("demoVid_b05", "UC_demo_b", "Ошибки новичков", "2026-08-15T12:00:00Z", 2300, 45, 7),
        _video("demoVid_c01", "UC_demo_c", "Первый ролик про ИИ", "2026-10-10T09:00:00Z", 400, 12, 2),
        _video("demoVid_c02", "UC_demo_c", "Нейросеть читает мои заметки", "2026-10-18T09:00:00Z", 900, 20, 3),
        _video("demoVid_c03", "UC_demo_c", "Тест генератора картинок", "2026-09-02T09:00:00Z", 350, None, None),
        _video("demoVid_d01", "UC_demo_d", "ChatGPT tutorial на русском: полный курс", "2026-10-05T15:00:00Z", 70000, 2800, 330),
        _video("demoVid_d02", "UC_demo_d", "Нейросети для работы: 10 сервисов", "2026-10-19T15:00:00Z", 21000, 800, 95),
        _video("demoVid_d03", "UC_demo_d", "Разбор промптов подписчиков", "2026-09-25T15:00:00Z", 19000, 700, 80),
        _video("demoVid_d04", "UC_demo_d", "Прямой эфир: вопросы про ИИ", "2026-09-15T15:00:00Z", 15000, 500, 300, live=True, duration="PT1H20M"),
        _video("demoVid_d05", "UC_demo_d", "Агенты на практике", "2026-09-01T15:00:00Z", 23000, 800, 90),
        _video("demoVid_e01", "UC_demo_comp", "Новости ИИ за неделю", "2026-10-22T08:00:00Z", 30000, 900, 110),
        _video("demoVid_e02", "UC_demo_comp", "Новая модель: честный тест", "2026-10-09T08:00:00Z", 41000, 1500, 160),
        _video("demoVid_e03", "UC_demo_comp", "Итоги сентября", "2026-09-10T08:00:00Z", 26000, 700, 70),
    ]
    searches = {
        "нейросеть": ["demoVid_a01", "demoVid_d01", "demoVid_b01", "demoVid_c01"],
        "ChatGPT": ["demoVid_a01", "demoVid_d02", "demoVid_b02", "demoVid_a02"],
        "нейросети для работы": ["demoVid_d01", "demoVid_a02", "demoVid_c02"],
    }
    # Закрытое видео: есть в списке загрузок, но videos.list его не возвращает.
    extra_uploads = {"UC_demo_b": [("demoVid_b99", "2026-10-20T12:00:00Z")]}
    return channels, v, searches, extra_uploads


def _en_world():
    channels = {
        "UC_demo_en1": ("AI Basics", 30000, False),
        "UC_demo_en2": ("Prompt Garage", 9000, False),
    }
    v = [
        _video("demoEn_a01", "UC_demo_en1", "ChatGPT tutorial for absolute beginners", "2026-10-11T10:00:00Z", 60000, 2000, 250),
        _video("demoEn_a02", "UC_demo_en1", "AI tools I use every day", "2026-09-18T10:00:00Z", 7000, 200, 30),
        _video("demoEn_a03", "UC_demo_en1", "Prompt tricks", "2026-09-01T10:00:00Z", 6500, 190, 20),
        _video("demoEn_b01", "UC_demo_en2", "AI for beginners: first steps", "2026-10-14T10:00:00Z", 3000, 90, 12),
        _video("demoEn_b02", "UC_demo_en2", "Ten useful AI tools", "2026-09-22T10:00:00Z", 2800, 80, 9),
    ]
    searches = {
        "AI tools": ["demoEn_a01", "demoEn_b01"],
        "ChatGPT tutorial": ["demoEn_a01", "demoEn_a02"],
        "AI for beginners": ["demoEn_b01", "demoEn_a02"],
    }
    return channels, v, searches, {}


class FakeHttp(httplib2.Http):
    """Отвечает как YouTube; все обращения складывает в `self.log`."""

    def __init__(self, world, reject_key=False, fail_from=None, fail=None):
        """`fail_from` — номер запроса, с которого YouTube отвечает `fail=(код, ответ)`."""
        super().__init__()
        self.fail_from, self.fail = fail_from, fail
        self.channels, self.videos, self.searches, self.extra = world
        self.reject_key = reject_key
        self.log = []

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        parsed = urlparse(uri)
        q = dict(parse_qsl(parsed.query))
        if self.reject_key:
            status, payload = 400, _key_error()
        elif self.fail_from is not None and len(self.log) >= self.fail_from:
            status, payload = self.fail
        else:
            status, payload = 200, self._route(parsed.path.rsplit("/", 1)[-1], q)
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        clean = urlencode([(k, val) for k, val in parse_qsl(parsed.query) if k not in STRIP])
        self.log.append({
            "request": {"body": None, "headers": {"accept": ["application/json"]},
                        "method": method, "uri": f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{clean}"},
            "response": {"body": {"string": content.decode()},
                         "headers": {"content-type": ["application/json; charset=UTF-8"]},
                         "status": {"code": status, "message": _REASON.get(status, "Bad Request")}},
        })
        resp = httplib2.Response({"status": str(status), "content-type": "application/json; charset=UTF-8"})
        return resp, content

    def _by_id(self, vid):
        return next(v for v in self.videos if v["id"] == vid)

    def _route(self, name, q):
        if name == "search":
            ids = self.searches[q["q"]][: int(q["maxResults"])]
            items = [self._search_item(self._by_id(i)) for i in ids]
            return {"kind": "youtube#searchListResponse", "etag": "demo", "regionCode": q["regionCode"],
                    "pageInfo": {"totalResults": len(items), "resultsPerPage": len(items)}, "items": items}
        if name == "videos":
            items = [self._video_item(self._by_id(i)) for i in q["id"].split(",")
                     if any(v["id"] == i for v in self.videos)]
            return {"kind": "youtube#videoListResponse", "etag": "demo",
                    "pageInfo": {"totalResults": len(items), "resultsPerPage": len(items)}, "items": items}
        if name == "channels":
            items = [self._channel_item(c) for c in q["id"].split(",") if c in self.channels]
            return {"kind": "youtube#channelListResponse", "etag": "demo",
                    "pageInfo": {"totalResults": len(items), "resultsPerPage": len(items)}, "items": items}
        if name == "playlistItems":
            cid = "UC" + q["playlistId"][2:]
            ups = [(v["id"], v["published"]) for v in self.videos if v["channel"] == cid]
            ups += self.extra.get(cid, [])
            ups.sort(key=lambda x: x[1], reverse=True)
            items = [{"kind": "youtube#playlistItem", "etag": "demo",
                      "contentDetails": {"videoId": i, "videoPublishedAt": p}}
                     for i, p in ups[: int(q["maxResults"])]]
            return {"kind": "youtube#playlistItemListResponse", "etag": "demo",
                    "pageInfo": {"totalResults": len(ups), "resultsPerPage": len(items)}, "items": items}
        raise AssertionError(name)

    def _search_item(self, v):
        return {"kind": "youtube#searchResult", "etag": "demo",
                "id": {"kind": "youtube#video", "videoId": v["id"]},
                "snippet": {"publishedAt": v["published"], "channelId": v["channel"], "title": v["title"],
                            "description": f"Описание ролика «{v['title']}»",
                            "channelTitle": self.channels[v["channel"]][0],
                            "liveBroadcastContent": "none", "publishTime": v["published"]}}

    def _video_item(self, v):
        stats = {"viewCount": str(v["views"]), "favoriteCount": "0"}
        if v["likes"] is not None:
            stats["likeCount"] = str(v["likes"])
        if v["comments"] is not None:
            stats["commentCount"] = str(v["comments"])
        item = {"kind": "youtube#video", "etag": "demo", "id": v["id"],
                "snippet": {"publishedAt": v["published"], "channelId": v["channel"], "title": v["title"],
                            "description": f"Описание ролика «{v['title']}»",
                            "channelTitle": self.channels[v["channel"]][0],
                            "liveBroadcastContent": "none"},
                "contentDetails": {"duration": v["duration"], "dimension": "2d", "definition": "hd"},
                "statistics": stats}
        if v["live"]:
            item["liveStreamingDetails"] = {"actualStartTime": v["published"], "actualEndTime": v["published"]}
        return item

    def _channel_item(self, cid):
        title, subs, hidden = self.channels[cid]
        count = sum(1 for v in self.videos if v["channel"] == cid) + len(self.extra.get(cid, []))
        stats = {"viewCount": "1000000", "videoCount": str(count), "hiddenSubscriberCount": hidden}
        if not hidden:
            stats["subscriberCount"] = str(subs)
        return {"kind": "youtube#channel", "etag": "demo", "id": cid, "snippet": {"title": title},
                "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}},
                "statistics": stats}


def _key_error():
    msg = "API key not valid. Please pass a valid API key."
    return {"error": {"code": 400, "message": msg,
                      "errors": [{"message": msg, "domain": "global", "reason": "badRequest"}],
                      "status": "INVALID_ARGUMENT",
                      "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                                   "reason": "API_KEY_INVALID", "domain": "googleapis.com",
                                   "metadata": {"service": "youtube.googleapis.com"}}]}}


_REASON = {200: "OK", 400: "Bad Request", 403: "Forbidden", 503: "Service Unavailable"}


def _quota_error():
    msg = ("The request cannot be completed because you have exceeded your "
           "<a href=\"/youtube/v3/getting-started#quota\">quota</a>.")
    return {"error": {"code": 403, "message": msg,
                      "errors": [{"message": msg, "domain": "youtube.quota",
                                  "reason": "quotaExceeded"}]}}


def _backend_error():
    msg = "The service is currently unavailable."
    return {"error": {"code": 503, "message": msg,
                      "errors": [{"message": msg, "domain": "global", "reason": "backendError"}],
                      "status": "UNAVAILABLE"}}


def _write(name, interactions):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        yaml.safe_dump({"interactions": interactions, "version": 1}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def _drive(http, region, language, keywords, competitors):
    """Те же вызовы, что делает сбор, чтобы запросы в кассете совпали с ним."""
    from datetime import datetime, timedelta, timezone

    from produce.core.collect import Cache, Plan, collect
    from produce.core.runs import Run
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp) / "cache"
        cache_dir.mkdir()
        run = Run(Path(tmp), {"quota_spent": 0, "requests_count": 0, "incomplete_data": []})
        api = YouTubeApi("fake-key-for-recording", http=http)
        plan = Plan("x", region, language, keywords, competitors)
        moment = datetime(2026, 10, 27, tzinfo=timezone.utc)
        assert moment - timedelta(days=30) < moment
        collect(run, plan, api, Cache(cache_dir), moment=moment)


def main():
    ru_words = ["нейросеть", "ChatGPT", "нейросети для работы"]
    ru = FakeHttp(_ru_world())
    _drive(ru, "RU", "ru", ru_words, [])
    _write("collect_ru.yaml", ru.log)
    # Со списком конкурентов запросы другие (список каналов и роликов длиннее): своя кассета.
    ru_comp = FakeHttp(_ru_world())
    _drive(ru_comp, "RU", "ru", ru_words, ["UC_demo_comp"])
    _write("collect_ru_competitors.yaml", ru_comp.log)
    en = FakeHttp(_en_world())
    _drive(en, "US", "en", ["AI tools", "ChatGPT tutorial", "AI for beginners"], [])
    _write("collect_en.yaml", en.log)
    bad = FakeHttp(_ru_world(), reject_key=True)
    try:
        _drive(bad, "RU", "ru", ["нейросеть", "ChatGPT", "нейросети для работы"], [])
    except Exception:  # noqa: BLE001 - отказ ключа здесь ожидаем
        pass
    _write("key_rejected.yaml", bad.log)
    # Отказы: YouTube лежит (первый запрос и 3 повтора), квота кончилась после 5-го запроса.
    # Пауза между повторами в скрипте не нужна.
    from produce.core import youtube
    youtube.pause = lambda seconds: None
    down = FakeHttp(_ru_world(), fail_from=0, fail=(503, _backend_error()))
    try:
        _drive(down, "RU", "ru", ru_words, [])
    except Exception:  # noqa: BLE001 - сбой здесь ожидаем
        pass
    _write("server_down.yaml", down.log)
    stop_after = 5  # 3 поиска, ролики, каналы; дальше списки загрузок
    day1 = FakeHttp(_ru_world(), fail_from=stop_after, fail=(403, _quota_error()))
    try:
        _drive(day1, "RU", "ru", ru_words, [])
    except Exception:  # noqa: BLE001 - квота кончилась, как задумано
        pass
    _write("quota_day1.yaml", day1.log)
    _write("quota_day2.yaml", ru.log[stop_after:])
    manifest = {
        name: {"recorded_at": RECORDED,
               "origin": "собрано вручную по формату официальных ответов YouTube Data API v3 "
                         "(scripts/make_demo_cassettes.py); заменить настоящими записями"}
        for name in ("collect_ru.yaml", "collect_ru_competitors.yaml", "collect_en.yaml",
                     "key_rejected.yaml", "server_down.yaml", "quota_day1.yaml", "quota_day2.yaml")
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")


if __name__ == "__main__":
    main()
