"""T24, круг 2: враждебные адреса обложки. Принимается только https://i.ytimg.com/… (точный хост)."""

import pytest

from produce.core.youtube import best_thumbnail

GOOD = "https://i.ytimg.com/vi/abc/hqdefault.jpg"

BAD = [
    "https://evil.example/vi/a/maxresdefault.jpg", "http://i.ytimg.com/vi/a/x.jpg",
    "file:///etc/passwd", "javascript:alert(1)", "data:image/png;base64,AAAA",
    "//i.ytimg.com/vi/a/x.jpg", "https://user@i.ytimg.com/vi/a/x.jpg",
    "https://user:pw@i.ytimg.com/vi/a/x.jpg", "https://i.ytimg.com:8080/vi/a/x.jpg",
    "https://i.ytimg.com:443/vi/a/x.jpg", "https://i.ytimg.com.evil.example/vi/a/x.jpg",
    "https://evil.example/i.ytimg.com/x.jpg", "https://x.i.ytimg.com/vi/a/x.jpg",
    "https://I.YTIMG.COM/vi/a/x.jpg", "https://i.ytimg.com/vi/a b/x.jpg",
    "https://i.ytimg.com/vi/a)/x.jpg", "https://i.ytimg.com/vi/(a/x.jpg",
    "https://i.ytimg.com/vi/[a]/x.jpg", 'https://i.ytimg.com/vi/a"/x.jpg',
    "https://i.ytimg.com/vi/a'/x.jpg", "https://i.ytimg.com/vi/a\\x.jpg",
    "https://i.ytimg.com/vi/a\nb/x.jpg", "https://i.ytimg.com/vi/a\r\n/x.jpg",
    "https://i.ytimg.com/vi/a\tb/x.jpg", "https://i.ytimg.com\\@evil.example/x.jpg",
    "https://i.ytimg.com@evil.example/x.jpg", "https://evil.example#@i.ytimg.com/x.jpg",
    "https://i.ytimg.com/vi/a/x.jpg>", " https://i.ytimg.com/x.jpg", "",
    "i.ytimg.com/vi/a/x.jpg", "https:i.ytimg.com/x.jpg", "HTTPS://evil.example/x.jpg",
]


@pytest.mark.parametrize("bad", BAD)
def test_hostile_url_gives_empty(bad):
    assert best_thumbnail({"maxres": {"url": bad}}) == ""


@pytest.mark.parametrize("raw", [5, 1.5, ["x"], None, {"url": GOOD}, True])
def test_non_string_url_gives_empty(raw):
    assert best_thumbnail({"high": {"url": raw}}) == ""


@pytest.mark.parametrize("ok", [
    "https://i.ytimg.com/vi/abc/maxresdefault.jpg", GOOD,
    "https://i.ytimg.com/vi/abc/hqdefault.jpg?v=64a1b2c3",
    "https://i.ytimg.com/vi_webp/abc/maxresdefault.webp",
    "https://i.ytimg.com/vi/abc_-X/default.jpg?sqp=-oaym&rs=AOn4",
])
def test_real_urls_not_falsely_rejected(ok):
    assert best_thumbnail({"maxres": {"url": ok}}) == ok


def test_falls_through_all_bad_sizes_to_first_good():
    t = {"maxres": {"url": BAD[0]}, "standard": {"url": BAD[5]}, "high": {"url": 7},
         "medium": {"url": GOOD}, "default": {"url": "https://i.ytimg.com/vi/z/default.jpg"}}
    assert best_thumbnail(t) == GOOD


def test_all_bad_gives_empty():
    assert best_thumbnail({s: {"url": BAD[1]} for s in ("maxres", "high", "default")}) == ""
