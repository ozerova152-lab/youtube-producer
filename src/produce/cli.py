"""Тонкий интерфейс: разбирает аргументы, вызывает ядро, печатает по-русски."""

from pathlib import Path
from typing import Annotated

import typer

from produce.core import analysis as analyzing
from produce.core import collect as collecting
from produce.core import comments as commenting
from produce.core import importing, quota, report, runs
from produce.core import virals as finding
from produce.core.errors import KeyMissingError, ProduceError, QuotaExceededError, RunError
from produce.core.settings import (
    get_segment,
    list_segments,
    load_api_key,
    load_settings,
    my_channel_id,
)
from produce.core.youtube import YouTubeApi

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


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@app.command()
def collect(
    ctx: typer.Context,
    segment: Annotated[str | None, typer.Option(help="Сегмент; если он один, берётся он")] = None,
    confirm: Annotated[bool, typer.Option(help="Слово человека получено: идти за данными")] = False,
    env_file: Annotated[Path, typer.Option(help="Файл с ключом YouTube")] = Path(".env"),
) -> None:
    """Оценить квоту (без флага) или собрать данные YouTube (`--confirm`)."""
    try:
        _collect(ctx.obj, segment, confirm, env_file)
    except ProduceError as err:
        raise _fail(err) from err


def _collect(channel: Path, segment_id: str | None, confirm: bool, env_file: Path) -> None:
    settings = load_settings(channel)
    ids = [str(s["id"]) for s in list_segments(settings)]
    if segment_id is None:
        if len(ids) != 1:
            raise RunError(f"Укажите сегмент: --segment ({', '.join(ids)})")
        segment_id = ids[0]
    segment = get_segment(settings, segment_id)
    plan = collecting.make_plan(settings, segment)

    key = load_api_key(env_file)
    if key is None:
        raise KeyMissingError(
            "Ключа YouTube нет. Можно (1) получить бесплатный ключ: шаги в README, "
            "и положить его в файл `.env` строкой YOUTUBE_API_KEY=ваш_ключ, "
            "или (2) загрузить видео из файла CSV/JSON. Что выбираете?"
        )

    month = runs.current_month(collecting.now().date())
    existing = runs.list_runs(channel, month, segment_id)
    run = existing[-1] if existing else runs.start_run(
        channel, month, segment_id, str(segment.get("language", "ru"))).run
    cache = collecting.Cache(run.path / "cache")
    ledger = quota.ledger_path(channel)

    typer.echo("Считаю расход квоты…")
    est = collecting.estimate(plan, cache)
    available = quota.remaining_today(ledger)
    runs.advance_stage(run, "оценка квоты")
    if est.total > available:
        runs.set_awaiting(run, False)
        raise ProduceError(
            f"Нужно ~{_num(est.total)}, доступно {_num(available)}. "
            "Продолжим завтра, прогресс сохранится"
        )
    if not confirm:
        runs.set_awaiting(run, True)
        typer.echo(
            f"Расход: ~{_num(est.total)} из {_num(quota.DAILY_LIMIT)} единиц "
            f"({est.searches} {_plural(est.searches, 'поиск', 'поиска', 'поисков')}, "
            f"{est.requests} {_plural(est.requests, 'запрос', 'запроса', 'запросов')}; "
            f"в сумму входит до {est.comment_units} на комментарии залётов). "
            "На сегодня хватает. Запускаем сбор?"
        )
        typer.echo("Жду вашего «да».")
        return

    runs.set_awaiting(run, False)
    api = YouTubeApi(key, on_request=lambda cost: runs.record_usage(run, cost, 1, ledger))
    try:
        summary = collecting.collect(run, plan, api, cache,
                                     progress=lambda text: typer.echo(f"Собираю: {text}…"))
    except QuotaExceededError:
        # До завтра квота считается потраченной: повторный запуск сегодня не стучится зря.
        quota.mark_exhausted(ledger)
        raise
    runs.advance_stage(run, "собрано")
    typer.echo(
        f"Собрано: {summary.videos} видео, {summary.channels} "
        f"{_plural(summary.channels, 'канал', 'канала', 'каналов')}. "
        f"Расход: {_num(summary.quota_spent)} ед. Обращений: {summary.requests}. "
        f"Неполные данные: {summary.incomplete} видео"
    )


@app.command(name="import")
def import_command(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="Файл CSV или JSON, формат в docs/import-format.md")],
    segment: Annotated[str | None, typer.Option(help="Сегмент; если он один, берётся он")] = None,
) -> None:
    """Загрузить видео и каналы из файла (без ключа YouTube, без обращений к сети)."""
    try:
        _import(ctx.obj, file, segment)
    except ProduceError as err:
        raise _fail(err) from err


def _import(channel: Path, file: Path, segment_id: str | None) -> None:
    settings = load_settings(channel)
    ids = [str(s["id"]) for s in list_segments(settings)]
    if segment_id is None:
        if len(ids) != 1:
            raise RunError(f"Укажите сегмент: --segment ({', '.join(ids)})")
        segment_id = ids[0]
    segment = get_segment(settings, segment_id)
    minimum = int((settings.get("thresholds") or {}).get("min_channel_videos",
                                                          importing.MIN_CHANNEL_VIDEOS))
    # Файл проверяется до создания запуска: неверный файл не оставляет следов.
    mine = my_channel_id(settings)
    importing.parse(file, minimum, mine)
    month = runs.current_month(collecting.now().date())
    existing = runs.list_runs(channel, month, segment_id)
    run = existing[-1] if existing else runs.start_run(
        channel, month, segment_id, str(segment.get("language", "ru"))).run
    result = importing.import_file(run, file, minimum, mine)
    typer.echo(
        f"Загружено: {len(result.videos)} видео, {len(result.channels)} "
        f"{_plural(len(result.channels), 'канал', 'канала', 'каналов')}. Обращений к YouTube: 0"
    )
    if result.skipped_channels:
        typer.echo(f"Каналов с менее чем {minimum} роликами: {len(result.skipped_channels)}, "
                   "они пропущены")
    if not result.comments:
        typer.echo("Комментариев нет: причины предположительные, по названиям и описаниям")


@app.command()
def virals(
    ctx: typer.Context,
    segment: Annotated[str | None, typer.Option(help="Сегмент; если он один, берётся он")] = None,
) -> None:
    """Найти залёты по кэшу запуска (без сети) и записать `virals.json`."""
    try:
        settings = load_settings(ctx.obj)
        ids = [str(s["id"]) for s in list_segments(settings)]
        if segment is None:
            if len(ids) != 1:
                raise RunError(f"Укажите сегмент: --segment ({', '.join(ids)})")
            segment = ids[0]
        get_segment(settings, segment)
        found = runs.list_runs(ctx.obj, runs.current_month(collecting.now().date()), segment)
        if not found:
            raise RunError(f"Запуска для сегмента {segment} ещё нет: сначала `produce collect`")
        result = finding.find_and_save(found[-1], settings)
    except ProduceError as err:
        raise _fail(err) from err
    typer.echo(f"Проверено видео: {result['checked']}. Залётов: {len(result['virals'])}")
    for v in result["virals"]:
        typer.echo(f"- {v['title']}: {_num(v['views'])} просмотров, норма {_num(v['norm'])}, "
                   f"{finding.times_text(v)}")
    if not result["virals"]:
        typer.echo("Залётов нет. Ближайшие 5 к порогу:")
        for v in result["nearest"]:
            typer.echo(f"- {v['title']}: {_num(v['views'])} просмотров, норма {_num(v['norm'])}, "
                       f"{finding.times_text(v)}")
        typer.echo("Могу предложить ослабить пороги в `settings.yaml`, "
                   "но менять его вы будете сами")
    if result["skipped"]:
        typer.echo(f"Мало данных: пропущено {len(result['skipped'])} видео")


@app.command(name="report")
def report_command(
    ctx: typer.Context,
    segment: Annotated[str | None, typer.Option(help="Сегмент; если он один, берётся он")] = None,
) -> None:
    """Собрать `report.md` запуска."""
    try:
        settings = load_settings(ctx.obj)
        ids = [str(s["id"]) for s in list_segments(settings)]
        if segment is None:
            if len(ids) != 1:
                raise RunError(f"Укажите сегмент: --segment ({', '.join(ids)})")
            segment = ids[0]
        get_segment(settings, segment)
        found = runs.list_runs(ctx.obj, runs.current_month(collecting.now().date()), segment)
        if not found:
            raise RunError(f"Запуска для сегмента {segment} ещё нет: сначала `produce collect`")
        report.write_report(found[-1], my_channel_id(settings))
        typer.echo(f"Отчёт записан: {found[-1].path / 'report.md'}")
    except ProduceError as err:
        raise _fail(err) from err


def _current_run(channel: Path, segment_id: str | None) -> tuple[dict, dict, runs.Run]:
    """Настройки, сегмент и последний запуск этого месяца; запуска нет — ошибка."""
    settings = load_settings(channel)
    ids = [str(s["id"]) for s in list_segments(settings)]
    if segment_id is None:
        if len(ids) != 1:
            raise RunError(f"Укажите сегмент: --segment ({', '.join(ids)})")
        segment_id = ids[0]
    segment = get_segment(settings, segment_id)
    found = runs.list_runs(channel, runs.current_month(collecting.now().date()), segment_id)
    if not found:
        raise RunError(f"Запуска для сегмента {segment_id} ещё нет: сначала `produce collect`")
    return settings, segment, found[-1]


@app.command()
def comments(
    ctx: typer.Context,
    segment: Annotated[str | None, typer.Option(help="Сегмент; если он один, берётся он")] = None,
    confirm: Annotated[bool, typer.Option(help="Слово человека получено: докачивать")] = False,
    env_file: Annotated[Path, typer.Option(help="Файл с ключом YouTube")] = Path(".env"),
) -> None:
    """Оценить расход (без флага) или докачать комментарии залётов (`--confirm`)."""
    try:
        _comments(ctx.obj, segment, confirm, env_file)
    except ProduceError as err:
        raise _fail(err) from err


def _comments(channel: Path, segment_id: str | None, confirm: bool, env_file: Path) -> None:
    settings, _, run = _current_run(channel, segment_id)
    limit, _ = commenting.limits_from(settings)
    ids = commenting.viral_ids(run)
    if not ids:
        raise RunError("Залётов нет: докачивать комментарии не у кого")
    todo = commenting.pending(run, ids)
    if not todo:
        typer.echo("Комментарии залётов уже собраны. Обращений к YouTube: 0")
        return

    key = load_api_key(env_file)
    if key is None:
        if run.data.get("source") == "import" and run.data.get("no_comments"):
            typer.echo("Комментариев нет: причины предположительные, по названиям и описаниям")
            return
        raise KeyMissingError(
            "Ключа YouTube нет. Можно (1) получить бесплатный ключ: шаги в README, "
            "и положить его в файл `.env` строкой YOUTUBE_API_KEY=ваш_ключ, "
            "или (2) загрузить видео из файла CSV/JSON. Что выбираете?"
        )

    units = commenting.estimate_units(len(todo))
    ledger = quota.ledger_path(channel)
    available = quota.remaining_today(ledger)
    if units > available:
        runs.set_awaiting(run, False)
        raise ProduceError(
            f"Нужно ~{_num(units)}, доступно {_num(available)}. Продолжим завтра, прогресс сохранится"
        )
    if not confirm:
        runs.set_awaiting(run, True)
        typer.echo(f"Комментарии {len(todo)} {_plural(len(todo), 'залёта', 'залётов', 'залётов')}: "
                   f"~{_num(units)} ед. Докачать?")
        typer.echo("Жду вашего «да».")
        return

    runs.set_awaiting(run, False)
    api = YouTubeApi(key, on_request=lambda cost: runs.record_usage(run, cost, 1, ledger))
    spent_before = int(run.data["quota_spent"])
    try:
        stored = commenting.fetch(run, api, ids, limit,
                                  progress=lambda text: typer.echo(f"Собираю: {text}…"))
    except QuotaExceededError:
        quota.mark_exhausted(ledger)
        raise QuotaExceededError(
            commenting.quota_message(int(run.data["quota_spent"]) - spent_before, units)
        ) from None
    total = sum(len(stored.get(i, [])) for i in ids)
    typer.echo(f"Комментарии собраны: {len(ids)} {_plural(len(ids), 'залёт', 'залёта', 'залётов')}, "
               f"{total} комментариев. Расход: {_num(int(run.data['quota_spent']) - spent_before)} ед.")


CHECK_STEPS = ("strategy", "briefs", "plan")


@app.command(name="check-files")
def check_files(
    ctx: typer.Context,
    step: Annotated[str | None, typer.Option(help="strategy, briefs или plan; без флага: разбор")] = None,
    segment: Annotated[str | None, typer.Option(help="Сегмент; если он один, берётся он")] = None,
) -> None:
    """Проверить структуру файлов агента по шаблонам (смысл проверяет человек)."""
    try:
        if step is not None and step not in CHECK_STEPS:
            raise RunError(f"Неизвестный шаг «{step}». Допустимые: {', '.join(CHECK_STEPS)}")
        if step is not None:
            raise RunError(f"Проверка шага «{step}» ещё не подключена: пока работает только "
                           "проверка разбора (`check-files` без `--step`)")
        settings, seg, run = _current_run(ctx.obj, segment)
        _, minimum = commenting.limits_from(settings)
        problems = analyzing.check(run, str(seg.get("language", "ru")), minimum)
    except ProduceError as err:
        raise _fail(err) from err
    if problems:
        for line in problems:
            typer.echo(line)
        raise typer.Exit(code=1)
    count = len(commenting.viral_ids(run))
    runs.advance_stage(run, "разбор готов")
    typer.echo(f"Проверено: разбор по {count} {_plural(count, 'залёту', 'залётам', 'залётам')}, ошибок нет")


if __name__ == "__main__":
    app()
