from pathlib import Path
from typing import Annotated

import typer

from produce.core.settings import SettingsError, load_settings

app = typer.Typer(add_completion=False, help="AI-продюсер YouTube-канала")


@app.callback(invoke_without_command=True)
def main(
    channel: Annotated[Path, typer.Option(help="Папка канала с settings.yaml")] = Path("data/default"),
) -> None:
    try:
        settings = load_settings(channel)
    except SettingsError as err:
        typer.echo(str(err))
        raise typer.Exit(code=1) from err
    segments = ", ".join(s["id"] for s in settings["segments"])
    typer.echo(f"Канал: {settings['channel']['name']}. Сегменты: {segments}")


if __name__ == "__main__":
    app()
