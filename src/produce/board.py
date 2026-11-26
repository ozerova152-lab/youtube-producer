"""Local, file-backed board for the user's existing producer runs.

The server does not run an AI agent, call YouTube or read credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import re
import secrets
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from produce.core import strategy
from produce.core.files import write_text_atomic

MAX_FILE = 2_000_000
MAX_BODY = 16_384
STATUSES = {"", "принят", "отклонён", "позже"}
RUN_NAME = re.compile(r"^\d{4}-\d{2}_[^/\\\x00]{1,120}_v\d{1,4}$")
ITEM_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
BRIEF_NAME = re.compile(r"^\d+\.md$")
STATUS_LINE = re.compile(r"^(- Статус:)(?:[ \t]*(принят|отклонён|позже))?[ \t]*(?=\r?$)", re.MULTILINE)
STRATEGY_LINE = re.compile(r"^(Статус: )(черновик|утверждена)(?=\r?$)", re.MULTILINE)
ANY_STATUS_LINE = re.compile(r"^[ \t]*[-*]?[ \t]*Статус[ \t]*:", re.MULTILINE | re.IGNORECASE)
DOCUMENTS = {
    "overview": "00-overview.md", "report": "report.md", "analysis": "analysis.md",
    "covers": "covers.md", "niche": "niche.md", "competitors": "candidates.md",
    "strategy": "strategy.md", "plan": "plan.md",
}
_LOCK = threading.RLock()


class BoardError(ValueError):
    """A safe error suitable for display without local paths or file contents."""


def _child(parent: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name or name in {".", ".."}
            or len(name) > 255 or any(ch in name for ch in "/\\\x00") or name.startswith(".")):
        raise BoardError("Некорректное имя")
    path = parent / name
    if path.is_symlink() or not path.resolve().is_relative_to(parent.resolve()):
        raise BoardError("Недоступный путь")
    return path


def _read(path: Path) -> bytes | None:
    if path.is_symlink():
        raise BoardError("Недоступный файл")
    try:
        if path.stat().st_size > MAX_FILE:
            raise BoardError("Файл слишком большой для просмотра")
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BoardError("Не удалось прочитать файл") from exc


def _strategy_status(text: str) -> str | None:
    """Recognize exactly the same status lines as the existing strategy checker."""
    found = [line for line in text.splitlines() if strategy._STATUS_LINE.match(line)]
    if len(found) != 1:
        return None
    match = strategy._STATUS_OK.fullmatch(found[0])
    return match.group(1) if match else None


def _revision(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeError as exc:
        raise BoardError("Не удалось прочитать файл") from exc


def _ideas(data: bytes) -> list[dict]:
    try:
        parsed = json.loads(_text(data))
        if not isinstance(parsed, dict) or parsed.get("version") != 1:
            raise ValueError
        ideas = parsed["ideas"]
        if not isinstance(ideas, list) or len(ideas) > 10000:
            raise ValueError
        seen = set()
        for idea in ideas:
            if (not isinstance(idea, dict) or not isinstance(idea.get("id"), str)
                    or not ITEM_NAME.fullmatch(idea["id"]) or idea["id"] in seen
                    or not isinstance(idea.get("title"), str) or not idea["title"].strip()
                    or not isinstance(idea.get("source"), str)
                    or idea.get("status") not in STATUSES):
                raise ValueError
            seen.add(idea["id"])
        return ideas
    except (ValueError, TypeError, KeyError) as exc:
        raise BoardError("Файл идей повреждён или имеет неподдерживаемый формат") from exc


@contextmanager
def _writer_lock(run: Path):
    # Local board writers cooperate via this lock. External agents must use the
    # same protocol; the revision check also catches edits already completed.
    with _LOCK:
        lock_path = _child(run, "board.lock")
        if lock_path.exists() and not lock_path.is_file():
            raise BoardError("Не удалось сохранить решение")
        with lock_path.open("a+b") as lock:
            try:
                import fcntl
            except ImportError:  # Windows native
                import msvcrt
                lock.seek(0, 2)
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class BoardStore:
    """Safe access to runs rooted below a single chosen channels directory."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _channel(self, channel: str) -> Path:
        path = _child(self.root, channel)
        if not path.is_dir():
            raise BoardError("Канал не найден")
        return path

    def _run(self, channel: str, run: str) -> Path:
        if not isinstance(run, str) or not RUN_NAME.fullmatch(run):
            raise BoardError("Некорректное имя запуска")
        runs = _child(self._channel(channel), "runs")
        path = _child(runs, run)
        if not path.is_dir():
            raise BoardError("Запуск не найден")
        return path

    def channels(self) -> list[str]:
        if not self.root.is_dir():
            return []
        try:
            return sorted(p.name for p in self.root.iterdir()
                          if p.is_dir() and not p.is_symlink() and not p.name.startswith("."))
        except OSError as exc:
            raise BoardError("Не удалось открыть список каналов") from exc

    def runs(self, channel: str) -> list[str]:
        base = _child(self._channel(channel), "runs")
        if not base.is_dir():
            return []
        try:
            return sorted((p.name for p in base.iterdir() if not p.is_symlink()
                           and p.is_dir() and RUN_NAME.fullmatch(p.name)), reverse=True)
        except OSError as exc:
            raise BoardError("Не удалось открыть список запусков") from exc

    def snapshot(self, channel: str, run: str) -> dict:
        base = self._run(channel, run)
        result = {"channel": channel, "run": run, "stage": None, "documents": {},
                  "ideas": [], "ideas_revision": None, "briefs": [], "video_data": {}, "warnings": []}
        try:
            raw = _read(_child(base, "run.json"))
            if raw is None:
                raise BoardError("Нет файла этапа")
            meta = json.loads(_text(raw))
            if not isinstance(meta, dict) or not isinstance(meta.get("stage"), str):
                raise TypeError
            result["stage"] = meta["stage"]
        except (BoardError, ValueError, TypeError):
            result["warnings"].append("Этап запуска недоступен или повреждён")
        for key, filename in DOCUMENTS.items():
            try:
                raw = _read(_child(base, filename))
                if raw is not None:
                    text = _text(raw)
                    info = {"content": text, "revision": _revision(raw), "source": filename}
                    if key == "strategy":
                        info["status"] = _strategy_status(text)
                    result["documents"][key] = info
            except BoardError:
                result["warnings"].append("Документ «" + filename + "» недоступен")
        for key in ("virals", "my_results"):
            try:
                raw = _read(_child(base, key + ".json"))
                if raw is not None:
                    data = json.loads(_text(raw))
                    if not isinstance(data, dict):
                        raise ValueError
                    result["video_data"][key] = data
            except (BoardError, ValueError, TypeError):
                result["warnings"].append("Данные видео недоступны или повреждены")
        try:
            raw = _read(_child(base, "ideas.json"))
            if raw is not None:
                result["ideas"] = _ideas(raw)
                result["ideas_revision"] = _revision(raw)
        except BoardError:
            result["warnings"].append("Идеи недоступны или имеют неподдерживаемый формат")
        try:
            briefs = _child(base, "briefs")
            if briefs.is_dir():
                for path in sorted(briefs.iterdir()):
                    if not BRIEF_NAME.fullmatch(path.name) or path.is_symlink():
                        continue
                    try:
                        raw = _read(path)
                        if raw is None:
                            continue
                        body = _text(raw)
                        lines = body.splitlines()
                        title = lines[0].removeprefix("# ") if lines else path.stem
                        statuses = STATUS_LINE.findall(body)
                        result["briefs"].append({"id": path.stem, "title": title,
                            "status": statuses[0][1] if len(statuses) == 1 else None,
                            "content": body, "revision": _revision(raw),
                            "source": "briefs/" + path.name})
                    except BoardError:
                        result["warnings"].append("Один из брифов недоступен")
        except (OSError, BoardError):
            result["warnings"].append("Список брифов недоступен")
        return result

    def save_ideas(self, channel: str, run: str, ideas: list[dict], revision: str | None) -> dict:
        """Save agent proposals without changing or removing a person's decisions."""
        base = self._run(channel, run)
        path = _child(base, "ideas.json")
        try:
            payload = json.dumps({"version": 1, "ideas": ideas}, ensure_ascii=False).encode("utf-8")
            if len(payload) > MAX_FILE:
                raise BoardError("Список идей слишком большой")
            proposed = _ideas(payload)
            with _writer_lock(base):
                current = _read(path)
                if ((current is None and revision is not None)
                        or (current is not None and (not isinstance(revision, str)
                            or not hmac.compare_digest(_revision(current), revision)))):
                    raise BoardError("Файл изменился. Обновите данные и повторите")
                previous = _ideas(current) if current is not None else []
                old_by_id = {idea["id"]: idea for idea in previous}
                new_by_id = {idea["id"]: idea for idea in proposed}
                if not old_by_id.keys() <= new_by_id.keys():
                    raise BoardError("Агент не может удалять прежние идеи")
                for idea in proposed:
                    old = old_by_id.get(idea["id"])
                    if old is None and idea["status"]:
                        raise BoardError("Агент не может принимать решения за человека")
                    if old is not None and (old["status"] != idea["status"]
                                            or (old["status"] and old != idea)):
                        raise BoardError("Агент не может изменять решение или выбранную идею")
                document = json.loads(_text(current)) if current is not None else {"version": 1}
                document["ideas"] = proposed
                updated = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
                if len(updated.encode("utf-8")) > MAX_FILE or _read(path) != current:
                    raise BoardError("Файл изменился или стал слишком большим")
                write_text_atomic(path, updated)
                return {"ok": True, "revision": _revision(updated.encode("utf-8"))}
        except (OSError, TypeError) as exc:
            raise BoardError("Не удалось сохранить идеи") from exc

    def decide(self, channel: str, run: str, kind: str, item: str,
               status: str, revision: str) -> dict:
        base = self._run(channel, run)
        if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{64}", revision):
            raise BoardError("Обновите страницу перед сохранением")
        if kind == "idea":
            if not isinstance(item, str) or not ITEM_NAME.fullmatch(item) or status not in STATUSES:
                raise BoardError("Недопустимое решение")
            path = _child(base, "ideas.json")
        elif kind == "brief":
            if not isinstance(item, str) or not re.fullmatch(r"\d+", item) or status not in STATUSES:
                raise BoardError("Недопустимое решение")
            path = _child(_child(base, "briefs"), item + ".md")
        elif kind == "strategy":
            if item != "strategy" or status not in {"черновик", "утверждена"}:
                raise BoardError("Недопустимое решение")
            path = _child(base, "strategy.md")
        else:
            raise BoardError("Недопустимый тип решения")
        try:
            with _writer_lock(base):
                raw = _read(path)
                if raw is None or not hmac.compare_digest(_revision(raw), revision):
                    raise BoardError("Файл изменился. Обновите страницу и повторите решение")
                if kind == "idea":
                    ideas = _ideas(raw)
                    matches = [x for x in ideas if x["id"] == item]
                    if len(matches) != 1:
                        raise BoardError("Идея не найдена")
                    data = json.loads(_text(raw))
                    matches[0]["status"] = status
                    # Mutate the validated list attached to the original object.
                    data["ideas"] = ideas
                    updated = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
                else:
                    text = _text(raw)
                    pattern = STATUS_LINE if kind == "brief" else STRATEGY_LINE
                    if kind == "strategy":
                        valid_status = _strategy_status(text) is not None
                    else:
                        valid_status = len(pattern.findall(text)) == 1 and len(ANY_STATUS_LINE.findall(text)) == 1
                    if not valid_status:
                        raise BoardError("Статус не распознан. Файл не изменён")
                    if kind == "brief":
                        updated = pattern.sub(lambda m: m.group(1) + (" " + status if status else ""), text, count=1)
                    else:
                        updated = pattern.sub(lambda m: m.group(1) + status, text, count=1)
                if _read(path) != raw:
                    raise BoardError("Файл изменился. Обновите страницу и повторите решение")
                write_text_atomic(path, updated)
                return {"ok": True, "revision": _revision(updated.encode("utf-8"))}
        except OSError as exc:
            raise BoardError("Не удалось сохранить решение. Повторите попытку") from exc


def valid_request(host: str, origin: str | None, port: int, mutation: bool,
                  supplied_token: str | None, token: str) -> bool:
    """Reject DNS rebinding and cross-origin writes; CORS is never enabled."""
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if host not in allowed_hosts:
        return False
    if origin is not None and origin != "http://" + host:
        return False
    return not (mutation and (origin is None or supplied_token is None
                              or not hmac.compare_digest(supplied_token.encode("utf-8"), token.encode("utf-8"))))


class BoardServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, store: BoardStore, port: int = 8765):
        super().__init__(("127.0.0.1", port), BoardHandler)
        self.store = store
        self.token = secrets.token_urlsafe(32)


class BoardHandler(BaseHTTPRequestHandler):
    server: BoardServer

    def log_message(self, format, *args):
        # URLs may contain private channel names, so suppress request logs.
        return

    def _reply(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: object) -> None:
        self._reply(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _allowed(self, mutation: bool = False) -> bool:
        return valid_request(self.headers.get("Host", ""), self.headers.get("Origin"),
                             self.server.server_port, mutation,
                             self.headers.get("X-Board-Token"), self.server.token)

    def do_GET(self) -> None:
        if not self._allowed():
            self._json(403, {"error": "Доступ запрещён"})
            return
        path = urlsplit(self.path).path
        parts = [unquote(x) for x in path.strip("/").split("/")]
        try:
            if path == "/api/session":
                self._json(200, {"token": self.server.token})
            elif path == "/api/channels":
                self._json(200, {"channels": self.server.store.channels()})
            elif len(parts) == 4 and parts[:2] == ["api", "channels"] and parts[3] == "runs":
                self._json(200, {"runs": self.server.store.runs(parts[2])})
            elif len(parts) == 5 and parts[:2] == ["api", "channels"] and parts[3] == "runs":
                self._json(200, self.server.store.snapshot(parts[2], parts[4]))
            elif path == "/" or (path.startswith("/assets/") and len(parts) == 2):
                name = "index.html" if path == "/" else parts[1]
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name.startswith("."):
                    raise BoardError("Страница не найдена")
                folder = Path(__file__).parent / "web_static"
                raw = _read(_child(folder, name))
                if raw is None:
                    self._json(404, {"error": "Страница пока недоступна"})
                else:
                    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    self._reply(200, raw, mime + ("; charset=utf-8" if mime.startswith("text/") else ""))
            else:
                self._json(404, {"error": "Страница не найдена"})
        except BoardError as exc:
            self._json(400, {"error": str(exc)})
        except (OSError, ValueError, TypeError):
            self._json(500, {"error": "Не удалось открыть данные"})

    def do_POST(self) -> None:
        if not self._allowed(mutation=True):
            self._json(403, {"error": "Доступ запрещён"})
            return
        parts = [unquote(x) for x in urlsplit(self.path).path.strip("/").split("/")]
        if (len(parts) != 6 or parts[:2] != ["api", "channels"]
                or parts[3] != "runs" or parts[5] != "decision"):
            self._json(404, {"error": "Действие не найдено"})
            return
        try:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise BoardError("Неверный формат запроса")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY:
                raise BoardError("Недопустимый размер запроса")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or set(data) != {"kind", "item", "status", "revision"}:
                raise BoardError("Неверные параметры решения")
            self._json(200, self.server.store.decide(parts[2], parts[4], **data))
        except BoardError as exc:
            self._json(409 if "изменился" in str(exc) else 400, {"error": str(exc)})
        except (ValueError, TypeError, UnicodeDecodeError):
            self._json(400, {"error": "Неверный формат запроса"})
        except OSError:
            self._json(500, {"error": "Не удалось сохранить решение"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальная доска YouTube Producer")
    parser.add_argument("--data-root", type=Path, default=Path.cwd() / "data",
                        help="Папка с каналами (по умолчанию data)")
    parser.add_argument("--port", type=int, default=8765, help="Локальный порт")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Порт должен быть от 0 до 65535")
    server = BoardServer(BoardStore(args.data_root), args.port)
    print(f"Доска: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
