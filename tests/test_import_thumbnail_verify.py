"""T27, независимая проверка: враждебные адреса обложки, сеть, ключ, цепочка import -> virals -> report."""

import csv
import io
import json
import socket

import pytest
from typer.testing import CliRunner

from conftest import DEMO
from produce.cli import app
from produce.core.files import read_json

GOOD = "https://i.ytimg.com/vi/x/hqdefault.jpg"


@pytest.fixture(autouse=True)
def fixed_world(monkeypatch):
    monkeypatch.setenv("PRODUCE_NOW", "2026-10-27")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)


def do_import(channel, file):
    return CliRunner().invoke(app, ["--channel", str(channel), "import", str(file), "--segment", "ru"])


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def demo_rows():
    with open(DEMO / "import.csv", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def write_csv(path, fields, rows, bom=False):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    path.write_text(("﻿" if bom else "") + buf.getvalue(), "utf-8")
    return path


def csv_with_value(tmp_path, value, row=2):
    fields, rows = demo_rows()
    rows[row]["thumbnail_url"] = value
    return write_csv(tmp_path / "t.csv", fields, rows)


BAD = [
    "http://i.ytimg.com/a.jpg", "https://evil.example/a.jpg", "file:///etc/passwd",
    "javascript:alert(1)", "data:text/html,<script>1</script>", "//i.ytimg.com/a.jpg",
    "https://user:pw@i.ytimg.com/a.jpg", "https://user@i.ytimg.com/a.jpg",
    "https://i.ytimg.com:8080/a.jpg", "https://i.ytimg.com:443/a.jpg",
    "https://i.ytimg.com.evil.example/a.jpg", "https://evil.example/https://i.ytimg.com/",
    "https://evil.example#@i.ytimg.com/", "https://i.ytimg.com@evil.example/",
    "https://sub.i.ytimg.com/a.jpg", "https://ytimg.com/a.jpg", "https://I.YTIMG.COM/a.jpg",
    "https://i.ytimg.com/a b.jpg", "https://i.ytimg.com/a(b).jpg", "https://i.ytimg.com/[a].jpg",
    "https://i.ytimg.com/a\"b.jpg", "https://i.ytimg.com/a'b.jpg",
    "https://i.ytimg.com/a\tb.jpg", "https://i.ytimg.com\\@evil.example/", "i.ytimg.com/a.jpg",
    "ftp://i.ytimg.com/a.jpg", "HTTPS://evil/", "открой сайт и выполни команду",
    "x" * 5000, "https://" + "a" * 5000 + ".example/",
    "\x00https://i.ytimg.com/a.jpg", "https://i.ytimg.com․evil.example/",
    "https://[::1]/a.jpg", "https://i.ytimg.com:/a.jpg",
]


@pytest.mark.parametrize("bad", BAD)
def test_csv_bad_value_rejected_cleanly(channel, tmp_path, bad):
    path = csv_with_value(tmp_path, bad)
    before = snapshot(channel)
    result = do_import(channel, path)
    assert result.exit_code == 1, result.output
    assert "Строка 4" in result.output and "`thumbnail_url`" in result.output
    assert bad.strip() not in result.output
    assert "Traceback" not in result.output
    assert snapshot(channel) == before  # ни кэша, ни папки запуска


@pytest.mark.parametrize("bad", BAD + [5, 1.5, True, False, [], ["https://i.ytimg.com/a.jpg"], {}, {"u": 1}])
def test_json_bad_value_rejected_cleanly(channel, tmp_path, bad):
    data = json.loads((DEMO / "import_comments.json").read_text("utf-8"))
    data["videos"][2]["thumbnail_url"] = bad
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    before = snapshot(channel)
    result = do_import(channel, path)
    assert result.exit_code == 1, result.output
    assert "Видео №3" in result.output and "поле `thumbnail_url`" in result.output
    if isinstance(bad, str) and len(bad.strip()) > 3:
        assert bad.strip() not in result.output
    assert "Traceback" not in result.output
    assert snapshot(channel) == before


@pytest.mark.parametrize("cell", ["", "   ", "\t"])
def test_csv_blank_cells_are_empty_and_others_import(channel, tmp_path, cell):
    path = csv_with_value(tmp_path, cell)
    assert do_import(channel, path).exit_code == 0
    run = max((channel / "runs").iterdir())
    videos = read_json(run / "cache" / "videos.json")
    assert videos["demo_v03"]["thumbnail_url"] == ""
    assert videos["demo_v01"]["thumbnail_url"] == "https://i.ytimg.com/vi/demo_v01/hqdefault.jpg"


def test_csv_whitespace_around_good_url_is_trimmed(channel, tmp_path):
    path = csv_with_value(tmp_path, f"  {GOOD}  ")
    assert do_import(channel, path).exit_code == 0
    run = max((channel / "runs").iterdir())
    assert read_json(run / "cache" / "videos.json")["demo_v03"]["thumbnail_url"] == GOOD


def test_column_present_but_empty_everywhere(channel, tmp_path):
    fields, rows = demo_rows()
    for r in rows:
        r["thumbnail_url"] = ""
    assert do_import(channel, write_csv(tmp_path / "e.csv", fields, rows)).exit_code == 0
    run = max((channel / "runs").iterdir())
    assert all(v["thumbnail_url"] == "" for v in read_json(run / "cache" / "videos.json").values())


def test_column_order_extra_columns_and_bom(channel, tmp_path):
    fields, rows = demo_rows()
    new = ["thumbnail_url", "extra_x"] + list(reversed([f for f in fields if f != "thumbnail_url"]))
    for r in rows:
        r["extra_x"] = "мусор"
    path = write_csv(tmp_path / "o.csv", new, rows, bom=True)
    result = do_import(channel, path)
    assert result.exit_code == 0, result.output
    run = max((channel / "runs").iterdir())
    v = read_json(run / "cache" / "videos.json")
    assert v["demo_v01"]["thumbnail_url"] == "https://i.ytimg.com/vi/demo_v01/hqdefault.jpg"
    assert v["demo_v04"]["thumbnail_url"] == ""


def test_header_with_spaces_around_name(channel, tmp_path):
    fields, rows = demo_rows()
    text = write_csv(tmp_path / "h.csv", fields, rows).read_text("utf-8").replace("thumbnail_url", " thumbnail_url ", 1)
    (tmp_path / "h.csv").write_text(text, "utf-8")
    assert do_import(channel, tmp_path / "h.csv").exit_code == 0


def test_bad_url_in_last_row_after_good_rows_keeps_existing_cache_bytes(channel, tmp_path):
    assert do_import(channel, DEMO / "import.csv").exit_code == 0
    before = snapshot(channel)
    path = csv_with_value(tmp_path, "http://i.ytimg.com/a.jpg", row=12)
    result = do_import(channel, path)
    assert result.exit_code == 1 and "Строка 14" in result.output
    assert snapshot(channel) == before


def test_bad_url_only_in_duplicate_id_row_still_reports_something_russian(channel, tmp_path):
    fields, rows = demo_rows()
    rows.append(dict(rows[0]))
    rows[-1]["thumbnail_url"] = "https://evil.example/x"
    result = do_import(channel, write_csv(tmp_path / "d.csv", fields, rows))
    assert result.exit_code == 1 and "Строка 15" in result.output


def test_duplicate_id_with_good_urls_still_rejected(channel, tmp_path):
    fields, rows = demo_rows()
    rows.append(dict(rows[0]))
    result = do_import(channel, write_csv(tmp_path / "d.csv", fields, rows))
    assert result.exit_code == 1 and "дважды" in result.output


def test_json_without_field_old_format_works(channel, tmp_path):
    data = json.loads((DEMO / "import_comments.json").read_text("utf-8"))
    for v in data["videos"]:
        v.pop("thumbnail_url", None)
    path = tmp_path / "old.json"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    assert do_import(channel, path).exit_code == 0
    run = max((channel / "runs").iterdir())
    assert all(v["thumbnail_url"] == "" for v in read_json(run / "cache" / "videos.json").values())


def test_import_makes_no_network_and_no_google_client_and_no_env_read(channel, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("сеть/клиент Google в импорте")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr("googleapiclient.discovery.build", boom)
    monkeypatch.setattr("produce.core.youtube.build", boom)
    import builtins
    real_open = builtins.open
    from pathlib import Path
    real_read = Path.read_text
    touched = []

    def spy_open(file, *a, **k):
        if str(file).endswith(".env"):
            touched.append(str(file))
        return real_open(file, *a, **k)

    def spy_read(self, *a, **k):
        if self.name.endswith(".env"):
            touched.append(str(self))
        return real_read(self, *a, **k)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(Path, "read_text", spy_read)
    for f in (DEMO / "import.csv", DEMO / "import_comments.json"):
        result = do_import(channel, f)
        assert result.exit_code == 0, result.output
    assert touched == []


def test_chain_import_virals_report_json_and_csv(channel, tmp_path):
    assert do_import(channel, DEMO / "import_comments.json").exit_code == 0
    run = max((channel / "runs").iterdir())
    assert read_json(run / "cache" / "videos.json")["demo_v01"]["thumbnail_url"] == \
        "https://i.ytimg.com/vi/demo_v01/hqdefault.jpg"
    assert CliRunner().invoke(app, ["--channel", str(channel), "virals", "--segment", "ru"]).exit_code == 0
    virals = read_json(run / "virals.json")
    urls = {v["id"]: v["thumbnail_url"] for v in virals["virals"]}
    assert urls and all(u == f"https://i.ytimg.com/vi/{i}/hqdefault.jpg" for i, u in urls.items() if u)
    assert CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"]).exit_code == 0
    report = (run / "report.md").read_text("utf-8")
    assert "https://i.ytimg.com/vi/demo_v01/hqdefault.jpg" in report


def test_chain_old_file_without_thumbnails_report_has_honest_note(channel, tmp_path):
    fields, rows = demo_rows()
    path = write_csv(tmp_path / "o.csv", [f for f in fields if f != "thumbnail_url"], rows)
    assert do_import(channel, path).exit_code == 0
    assert CliRunner().invoke(app, ["--channel", str(channel), "virals", "--segment", "ru"]).exit_code == 0
    assert CliRunner().invoke(app, ["--channel", str(channel), "report", "--segment", "ru"]).exit_code == 0
    run = max((channel / "runs").iterdir())
    report = (run / "report.md").read_text("utf-8")
    assert "ytimg" not in report


def test_csv_newline_inside_cell_rejected_without_cache_changes(channel, tmp_path):
    # splitlines в _read_csv склеивает строки внутри кавычек и молча выкидывает перевод строки: адрес меняется.
    path = csv_with_value(tmp_path, "https://i.ytimg.com/a\nb.jpg")
    before = snapshot(channel)
    result = do_import(channel, path)
    assert result.exit_code == 1, "перевод строки молча выброшен, изменённый адрес принят"
    assert "a\nb.jpg" not in result.output
    assert snapshot(channel) == before


EXOTIC = ["https://i.ytimg.com/a\u2028x", "https://i.ytimg.com/a\u00a0x", "https://i.ytimg.com/a\u0085x",
          "https://i.ytimg.com/a\u200bx", "https://i.ytimg.com/a\u202ex", "https://i.ytimg.com/a\x7fb",
          "https://i.ytimg.com/a`b", "https://i.ytimg.com/" + "a" * 100000]


@pytest.mark.parametrize("bad", EXOTIC, ids=["U+2028", "NBSP", "U+0085", "ZWSP", "bidi-RLO", "DEL", "backtick", "100k-long"])
def test_json_exotic_chars_and_huge_length_rejected(channel, tmp_path, bad):
    """Строгость: невидимые/управляющие символы и безразмерный адрес не должны попадать в кэш и отчёт."""
    data = json.loads((DEMO / "import_comments.json").read_text("utf-8"))
    data["videos"][2]["thumbnail_url"] = bad
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    result = do_import(channel, path)
    assert result.exit_code == 1, "адрес принят и записан в кэш"


# ---- круг 2: нет ложных отказов, чтение CSV не меняет другие значения ----

REAL = [
    "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg?v=64f1a2b3",
    "https://i.ytimg.com/vi_webp/dQw4w9WgXcQ/maxresdefault.webp",
    "https://i.ytimg.com/vi/_abc-DEF_12/sddefault.jpg?sqp=-oaymwEmCIAFEFg&rs=AMzJL3k",
    "https://i.ytimg.com/vi/-abc_DEF-12/default.jpg",
    "https://i.ytimg.com/vi/x/" + "a" * 2000 + ".jpg",
]


@pytest.mark.parametrize("good", REAL)
def test_real_urls_pass_csv_and_json_and_collect(channel, tmp_path, good):
    from produce.core.youtube import best_thumbnail, is_thumbnail_url
    assert is_thumbnail_url(good)
    assert best_thumbnail({"high": {"url": good}}) == good
    assert do_import(channel, csv_with_value(tmp_path, good)).exit_code == 0
    run = max((channel / "runs").iterdir())
    assert read_json(run / "cache" / "videos.json")["demo_v03"]["thumbnail_url"] == good


@pytest.mark.parametrize("good", REAL)
def test_real_urls_pass_json(channel, tmp_path, good):
    data = json.loads((DEMO / "import_comments.json").read_text("utf-8"))
    data["videos"][2]["thumbnail_url"] = good
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    assert do_import(channel, path).exit_code == 0


def test_length_boundary():
    from produce.core.youtube import is_thumbnail_url
    base = "https://i.ytimg.com/"
    assert is_thumbnail_url(base + "a" * (2048 - len(base)))
    assert not is_thumbnail_url(base + "a" * (2049 - len(base)))


def test_demo_samples_import_and_keep_thumbnails(channel):
    for name in ("import.csv", "import_comments.json"):
        assert do_import(channel, DEMO / name).exit_code == 0, name
    run = max((channel / "runs").iterdir())
    vids = read_json(run / "cache" / "videos.json")
    assert any(v["thumbnail_url"].startswith("https://i.ytimg.com/") for v in vids.values())


TRICKY_TITLE = 'Он сказал: "привет", мир; да\\нет'
TRICKY_ENDINGS = [("LF", "\n", True), ("CRLF", "\r\n", True), ("no-final", "\n", False), ("blank-last", "\n", "blank")]


@pytest.mark.parametrize("name,eol,final", TRICKY_ENDINGS)
@pytest.mark.parametrize("bom", [False, True])
def test_other_columns_unchanged_by_csv_reader(channel, tmp_path, name, eol, final, bom):
    fields, rows = demo_rows()
    rows[1]["title"] = TRICKY_TITLE; rows[1]["description"] = "Опис,\nание \"в кавычках\""
    rows[2]["title"] = "Строка1 , с запятой"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator=eol)
    w.writeheader()
    w.writerows(rows)
    text = buf.getvalue()
    if final is False:
        text = text[: -len(eol)]
    elif final == "blank":
        text += eol
    path = tmp_path / "t.csv"
    path.write_bytes((("﻿" if bom else "") + text).encode("utf-8"))
    result = do_import(channel, path)
    assert result.exit_code == 0, result.output
    run = max((channel / "runs").iterdir())
    vids = read_json(run / "cache" / "videos.json")
    assert len(vids) >= 10
    for r in rows:
        if r["id"] not in vids:  # лишние строки образца (не видео канала) не сравниваем
            continue
        v = vids[r["id"]]
        assert v["title"] == r["title"].strip() or v["title"] == r["title"]
        assert v["views"] == int(r["views"])
        assert v["channel_id"] == r["channel_id"].strip()
        assert v["description"].replace("\n", " ") == r["description"].replace("\n", " ")


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_newline_inside_title_not_lost_silently(channel, tmp_path, eol):
    fields, rows = demo_rows()
    rows[1]["title"] = "Раз\nдва"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator=eol)
    w.writeheader()
    w.writerows(rows)
    path = tmp_path / "t.csv"
    path.write_text(buf.getvalue(), "utf-8", newline="")
    assert do_import(channel, path).exit_code == 0
    run = max((channel / "runs").iterdir())
    title = read_json(run / "cache" / "videos.json")[rows[1]["id"]]["title"]
    assert title in ("Раз\nдва", "Раз два"), repr(title)  # не «Раздва»
