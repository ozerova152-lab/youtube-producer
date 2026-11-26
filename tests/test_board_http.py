"""HTTP contract against a loopback server in an isolated subprocess."""

import subprocess
import sys


def test_local_http_contract(tmp_path):
    script = r"""
import http.client
import json
import sys
import threading
from pathlib import Path
from produce.board import BoardServer, BoardStore
root = Path(sys.argv[1])
run = root / "one" / "runs" / "2026-10_ru_v1"
run.mkdir(parents=True)
(run / "run.json").write_text(json.dumps({"stage": "настроен"}))
(run / "ideas.json").write_text(json.dumps({"version": 1, "ideas": [{"id": "i-1", "title": "idea", "source": "demo", "status": ""}]}))
server = BoardServer(BoardStore(root), 0)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
port = server.server_port
connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
def request(method, path, body=None, headers=None):
    connection.request(method, path, body, headers or {})
    response = connection.getresponse()
    return response.status, json.loads(response.read())
try:
    code, session = request("GET", "/api/session")
    assert code == 200 and session["token"]
    base = "/api/channels/one/runs/2026-10_ru_v1"
    code, data = request("GET", base)
    assert code == 200 and data["ideas"][0]["title"] == "idea"
    decision = json.dumps({"kind": "idea", "item": "i-1", "status": "принят", "revision": data["ideas_revision"]}, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json", "X-Board-Token": session["token"], "Origin": "http://evil.example"}
    assert request("POST", base + "/decision", decision, headers)[0] == 403
    headers["Origin"] = "http://127.0.0.1:" + str(port)
    assert request("POST", base + "/decision", decision, headers)[0] == 200
    assert request("POST", base + "/decision", decision, headers)[0] == 409
    assert request("GET", "/api/channels/%2e%2e/runs")[0] == 400
    assert request("GET", base)[1]["ideas"][0]["status"] == "принят"
finally:
    connection.close()
    server.shutdown()
    server.server_close()
    thread.join()
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
