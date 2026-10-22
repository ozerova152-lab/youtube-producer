from pathlib import Path

from typer.testing import CliRunner

from produce.cli import app

DEMO = Path(__file__).parent.parent / "examples" / "demo"


def test_demo_channel_shows_segments():
    result = CliRunner().invoke(app, ["--channel", str(DEMO)])
    assert result.exit_code == 0
    assert "Сегменты: ru, en" in result.output


def test_missing_settings_gives_clear_message(tmp_path):
    result = CliRunner().invoke(app, ["--channel", str(tmp_path)])
    assert result.exit_code == 1
    assert "Не найден файл настроек" in result.output
