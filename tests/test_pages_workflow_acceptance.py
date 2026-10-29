"""Независимая приёмка T19: workflow Pages и раздел в setup.md, по критериям задачи (сети нет)."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows" / "pages.yml"
SETUP = ROOT / "docs" / "dev" / "setup.md"


def _wf() -> dict:
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _on(wf: dict) -> dict:
    return wf.get("on", wf.get(True))


def _all_uses(wf: dict) -> list[str]:
    return [s["uses"] for j in wf["jobs"].values() for s in j["steps"] if "uses" in s]


def test_makefile_check_runs_pytest_over_tests_dir():
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^check:.*\n(?:\t.*\n)*?\t\$\(BIN\)/pytest", mk, re.MULTILINE)
    assert "pyyaml" in (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()


def test_no_fork_or_pr_triggers_anywhere():
    text = WF.read_text(encoding="utf-8")
    on = _on(_wf())
    for bad in ("pull_request", "pull_request_target", "workflow_run", "issue_comment", "schedule"):
        assert bad not in on
    assert "github.event.pull_request" not in text
    assert "head_ref" not in text and "head.repo" not in text
    assert "tags" not in on["push"]
    assert "branches-ignore" not in on["push"]


def test_push_branch_is_exactly_main_without_wildcards():
    branches = _on(_wf())["push"]["branches"]
    assert branches == ["main"]


def test_no_write_permissions_beyond_pages_and_idtoken():
    wf = _wf()
    allowed_write = {"pages", "id-token"}
    for perms in [wf["permissions"]] + [j.get("permissions", {}) for j in wf["jobs"].values()]:
        assert isinstance(perms, dict), "permissions: write-all / read-all строкой недопустимо"
        for scope, level in perms.items():
            if level == "write":
                assert scope in allowed_write, scope
    assert wf["permissions"] == {"contents": "read"}


def test_workflow_level_permissions_do_not_grant_pages_write():
    assert "pages" not in _wf()["permissions"]
    assert "id-token" not in _wf()["permissions"]


def test_artifact_path_is_site_not_repo_root():
    for j in _wf()["jobs"].values():
        for s in j["steps"]:
            if "upload-pages-artifact" in s.get("uses", ""):
                path = str(s.get("with", {}).get("path", "."))
                assert path.strip("./") == "site"
    assert (ROOT / "site" / "index.html").is_file()


def test_no_secrets_tokens_or_remote_scripts():
    text = WF.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert not re.search(r"\b(curl|wget|iwr|Invoke-WebRequest)\b", text)
    assert "run:" not in text, "произвольных shell-шагов быть не должно"


def test_only_official_actions_with_full_sha_and_version_comment():
    text = WF.read_text(encoding="utf-8")
    uses = _all_uses(_wf())
    assert {"configure-pages", "upload-pages-artifact", "deploy-pages"} <= {
        u.split("@")[0].split("/")[1] for u in uses
    }
    for u in uses:
        name, ref = u.split("@")
        assert name.split("/")[0] == "actions"
        assert re.fullmatch(r"[0-9a-f]{40}", ref)
    for line in text.splitlines():
        if "uses:" in line:
            assert re.search(r"#\s*v\d+\.\d+\.\d+", line), line


def test_concurrency_group_pages_no_cancel():
    wf = _wf()
    assert wf["concurrency"] == {"group": "pages", "cancel-in-progress": False}
    for j in wf["jobs"].values():
        assert j.get("concurrency", wf["concurrency"])["cancel-in-progress"] is not True


def test_deploy_uses_github_pages_environment():
    (job,) = _wf()["jobs"].values()
    assert job["environment"]["name"] == "github-pages"


def test_setup_md_explains_public_repo_and_pages_source():
    text = SETUP.read_text(encoding="utf-8")
    m = re.search(r"^## [^\n]*[Пп]убликаци[^\n]*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    assert m, "нет раздела про публикацию витрины"
    section = m.group(1)
    assert "публичн" in section
    assert "Settings" in section and "Pages" in section
    assert "GitHub Actions" in section
    assert "pages.yml" in section


@pytest.mark.parametrize(
    "mutation",
    [
        lambda t: t.replace("branches: [main]", "branches: [main, dev]"),
        lambda t: t.replace("path: site", "path: ."),
        lambda t: t.replace("cancel-in-progress: false", "cancel-in-progress: true"),
        lambda t: t.replace("workflow_dispatch:", "pull_request_target:"),
        lambda t: t.replace("steps:", "steps:\n      - run: echo ${{ secrets.X }}", 1),
    ],
)
def test_sanity_mutated_workflows_would_be_caught(mutation):
    """Страховка от пустышки: на испорченном файле хотя бы одна проверка обязана упасть."""
    good = WF.read_text(encoding="utf-8")
    bad = mutation(good)
    assert bad != good
    wf = yaml.safe_load(bad)
    on = _on(wf)
    up = [s for j in wf["jobs"].values() for s in j["steps"] if "upload-pages" in s.get("uses", "")]
    ok = (
        on["push"]["branches"] == ["main"]
        and set(on) == {"push", "workflow_dispatch"}
        and wf["concurrency"]["cancel-in-progress"] is False
        and up[0]["with"]["path"] == "site"
        and "secrets." not in bad
    )
    assert not ok
