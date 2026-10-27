"""Тонкий интерфейс: разбирает аргументы, вызывает ядро, печатает по-русски."""

from pathlib import Path
from typing import Annotated

import typer

from produce.core import runs
from produce.core.errors import ProduceError, RunError
from produce.core.settings import get_segment, list_segments, load_settings

app = typer.Typer(add_completion=False, help="AI-продюсер YouTube-канала")


def _fail(err: ProduceError) -> typer.Exit:
    typer.echo(str(err))
    return typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    channel: Annotated[Path, typer.Option(help="Папка канала с settings.yaml")] = Path("data/default"),
) -> None:
    ctx.obj = channel
    if ctx.invoked_subcommand is not None:
        return
    try:
        settings = load_settings(channel)
    except ProduceError as err:
        raise _fail(err) from err
    segments = ", ".join(str(s["id"]) for s in list_segments(settings))
    typer.echo(f"Канал: {settings['channel']['name']}. Сегменты: {segments}")


@app.command()
def segments(ctx: typer.Context) -> None:
    """Показать сегменты из settings.yaml."""
    try:
        settings = load_settings(ctx.obj)
    except ProduceError as err:
        raise _fail(err) from err
    for s in list_segments(settings):
        typer.echo(f"{s['id']}: регион {s.get('region', '—')}, язык {s.get('language', '—')}")


@app.command()
def start(
    ctx: typer.Context,
    segment: Annotated[str | None, typer.Option(help="Сегмент; без флага спросим")] = None,
    brief_lang: Annotated[str | None, typer.Option(help="Язык брифа; без флага спросим")] = None,
    month: Annotated[str | None, typer.Option(help="Месяц ГГГГ-ММ; по умолчанию текущий")] = None,
    new_version: Annotated[bool, typer.Option(help="Прямая просьба: создать новую версию")] = False,
) -> None:
    """Найти или создать запуск месяца и сегмента."""
    try:
        settings = load_settings(ctx.obj)
        ids = [str(s["id"]) for s in list_segments(settings)]
        if segment is None:
            segment = typer.prompt(f"Сегменты: {', '.join(ids)}. Какой берём?")
        seg = get_segment(settings, segment)
        seg_lang = str(seg.get("language", "ru"))
        if brief_lang is None:
            brief_lang = typer.prompt(
                f"Язык брифа: язык сегмента ({seg_lang}) или русский (ru)?", default=seg_lang
            )
        if brief_lang not in {seg_lang, "ru"}:
            raise RunError(f"Язык брифа «{brief_lang}» не подходит: можно {seg_lang} или ru")
        month = month or runs.current_month()
        previous = runs.list_runs(ctx.obj, month, segment)
        if not previous:
            typer.echo(f"За {month} для сегмента {segment} ещё нет запуска. Создаю…")
        elif previous[-1].finished or new_version:
            typer.echo(
                f"В этом месяце уже есть v{previous[-1].data['version']}: "
                "создам новую версию, кэш скопирую, квота не тратится"
            )
        result = runs.start_run(ctx.obj, month, segment, brief_lang, new_version)
    except ProduceError as err:
        raise _fail(err) from err
    data = result.run.data
    if result.action == "resume":
        typer.echo(
            f"Запуск {data['month']}, {data['segment']}, v{data['version']}. "
            f"Этап: {data['stage']}. Продолжить?"
        )
    else:
        typer.echo(f"Запуск {result.run.path.name} создан. Этап: {data['stage']}")


if __name__ == "__main__":
    app()
