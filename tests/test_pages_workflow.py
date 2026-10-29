"""Статическая проверка .github/workflows/pages.yml (T19): сети нет, workflow не запускается."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / ".github" / "workflows" / "pages.yml"
OFFICIAL_PAGES = {"configure-pages", "upload-pages-artifact", "deploy-pages"}


def _load() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    # PyYAML читает ключ `on` как булево True
    return wf.get("on", wf.get(True))


def _steps(wf: dict) -> list[dict]:
    return [s for job in wf["jobs"].values() for s in job["steps"]]


def test_file_is_valid_yaml():
    assert isinstance(_load(), dict)


def test_triggers_only_push_main_and_manual():
    on = _triggers(_load())
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"]["branches"] == ["main"]
    assert set(on["push"]["paths"]) == {"site/**", ".github/workflows/pages.yml"}


def test_permissions_minimal():
    wf = _load()
    assert wf["permissions"] == {"contents": "read"}
    (job,) = wf["jobs"].values()
    assert job["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}


def test_publishes_only_site_folder():
    uploads = [s for s in _steps(_load()) if "upload-pages-artifact" in s.get("uses", "")]
    assert len(uploads) == 1
    assert uploads[0]["with"]["path"] in ("site", "site/", "./site")


def test_no_secrets_and_no_pipe_to_shell():
    text = PATH.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert "pull_request_target" not in text
    assert not re.search(r"(curl|wget)[^\n]*\|\s*(ba)?sh", text)


def test_only_official_actions_pinned_by_full_hash():
    uses = [s["uses"] for s in _steps(_load()) if "uses" in s]
    names = {u.split("@")[0] for u in uses}
    assert {f"actions/{n}" for n in OFFICIAL_PAGES} <= names
    for u in uses:
        name, _, ref = u.partition("@")
        assert name.startswith("actions/"), u
        assert re.fullmatch(r"[0-9a-f]{40}", ref), u


def test_concurrency_does_not_cancel_running_publish():
    c = _load()["concurrency"]
    assert c["group"] == "pages"
    assert c["cancel-in-progress"] is False
