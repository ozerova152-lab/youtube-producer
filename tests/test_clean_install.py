"""T15: чистая копия репозитория проходит шаги README до оценки квоты.

Копия делается из файлов, которые попали бы в git (без `.venv`, `data/`, `.env`, `runs/`):
так проверяется, что для первого запуска не нужно ничего, чего нет в репозитории.
Настоящие `make setup` (загрузка пакетов и Chromium) и сеть не используются: берётся
текущее окружение, но код запускается из копии.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "FAKE-KEY-for-clean-install-test-0000"


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    return [Path(p) for p in out.split("\0") if p and (ROOT / p).is_file()]


def _copy_repo(dst: Path) -> None:
    for rel in _tracked_files():
        if rel.parts[0] in {"docs", "test-results"}:
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)


def _produce(copy: Path, *args: str) -> subprocess.CompletedProcess:
    # Код берётся из копии: её src ставится первым в sys.path, раньше установленного пакета.
    code = (
        "import sys; sys.path.insert(0, sys.argv.pop(1)); import produce; "
        "print(produce.__file__, file=sys.stderr); from produce.cli import app; app()"
    )
    env = {"PATH": "/usr/bin:/bin", "HOME": str(copy)}
    return subprocess.run(
        [sys.executable, "-c", code, str(copy / "src"), *args], check=False, cwd=copy, env=env,
        capture_output=True, text=True, timeout=60,
    )


def test_readme_steps_reach_quota_estimate_on_clean_copy(tmp_path):
    copy = tmp_path / "youtube-producer"
    _copy_repo(copy)
    assert not (copy / ".venv").exists() and not (copy / "data").exists()
    assert not (copy / ".env").exists() and (copy / ".env.example").is_file()

    # README, шаг 2: cp .env.example .env и вписать ключ (здесь фиктивный, только в файле копии).
    env_text = (copy / ".env.example").read_text(encoding="utf-8")
    values = [
        line.split("=", 1)[1].strip() for line in env_text.splitlines()
        if "=" in line and not line.startswith("#")
    ]
    # В шаблоне допустим только явный заменитель, не настоящий ключ.
    assert "YOUTUBE_API_KEY" in env_text and all(v == "" or v.startswith("your-") for v in values)
    (copy / ".env").write_text(f"YOUTUBE_API_KEY={FAKE_KEY}\n", encoding="utf-8")

    # README, шаг 4: тестовый канал копируется в data/demo.
    shutil.copytree(copy / "examples/demo", copy / "data/demo")

    started = _produce(copy, "--channel", "data/demo", "start", "--segment", "ru", "--brief-lang", "ru")
    assert started.returncode == 0, started.stdout + started.stderr
    assert str(copy / "src") in started.stderr, "запущен не код копии"

    estimate = _produce(copy, "--channel", "data/demo", "collect", "--segment", "ru")
    out = estimate.stdout
    assert "Расход: ~" in out and "из 10 000" in out and "Запускаем сбор?" in out, out + estimate.stderr
    assert FAKE_KEY not in out + estimate.stderr

    run_json = next((copy / "data/demo/runs").glob("*/run.json"))
    data = json.loads(run_json.read_text(encoding="utf-8"))
    assert data["awaiting_confirmation"] is True
    assert data["requests_count"] == 0 and data["quota_spent"] == 0
    assert FAKE_KEY not in run_json.read_text(encoding="utf-8")


def test_env_and_data_ignored_and_env_example_has_no_real_value():
    for path in (".env", "data/demo/x"):
        res = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
        assert res.returncode == 0, path
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.split()
    assert ".env" not in tracked and not any(p.startswith("data/") for p in tracked)
