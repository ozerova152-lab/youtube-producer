"""Статическая проверка .github/dependabot.yml: сети нет, Dependabot не запускается."""

from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parent.parent / ".github" / "dependabot.yml"


def test_dependabot_checks_pip_and_github_actions_weekly():
    config = yaml.safe_load(PATH.read_text(encoding="utf-8"))
    assert config["version"] == 2
    updates = {u["package-ecosystem"]: u for u in config["updates"]}
    assert set(updates) == {"pip", "github-actions"}
    for update in updates.values():
        assert update["directory"] == "/"
        assert update["schedule"]["interval"] == "weekly"
