"""Отчёт запуска `report.md`: секции добавляются по мере появления данных."""

from produce.core import my_results, runs
from produce.core.collect import Cache, summarize
from produce.core.errors import RunError
from produce.core.files import read_json, write_json_atomic, write_text_atomic
from produce.core.virals import times_text


def _cell(text: object) -> str:
    """Название видео — чужой текст: без переводов строк и `|`, чтобы таблица не ломалась."""
    return " ".join(str(text).replace("|", "/").split())


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _virals_section(run: runs.Run) -> list[str]:
    path = run.path / "virals.json"
    if not path.exists():
        return []
    data = read_json(path)
    lines = ["## Залёты", ""]
    if data["virals"]:
        lines += ["| Название | Просмотры | Норма канала | Во сколько раз выше | Лайки | Комментарии | В день |",
                  "|----------|-----------|--------------|---------------------|-------|-------------|--------|"]
        for v in data["virals"]:
            lines.append(
                f"| [{_cell(v['title'])}]({v['url']}) | {_num(v['views'])} | {_num(v['norm'])} | "
                f"{times_text(v)} | {v['likes_ratio']:.1%} | {v['comments_ratio']:.2%} | "
                f"{_num(v['views_per_day'])} |")
        lines += ["", "«В день» — скорость набора просмотров, дополнительный сигнал: на отбор не влияет.", ""]
    else:
        lines += ["Залётов нет. Ближайшие 5 к порогу:", ""]
        for v in data["nearest"]:
            lines.append(f"- {_cell(v['title'])}: {_num(v['views'])} просмотров, норма "
                         f"{_num(v['norm'])}, {times_text(v)}")
        lines += ["", "Могу предложить ослабить пороги в `settings.yaml`, но менять его вы будете сами.", ""]
    if data["skipped"]:
        lines += [(f"Мало данных: пропущено {len(data['skipped'])} видео "
                   "(у канала меньше обычных роликов, чем нужно для нормы)."), ""]
    return lines


def _count(n: int | None) -> str:
    return _num(n) if n is not None else "—"


def _my_table(title: str, items: list[dict]) -> list[str]:
    lines = [f"### {title}", "", "| Название | Просмотры | Лайки | Комментарии | Опубликовано |",
             "|----------|-----------|-------|-------------|--------------|"]
    for v in items:
        lines.append(f"| [{_cell(v['title'])}]({v['url']}) | {_num(v['views'])} | "
                     f"{_count(v['likes'])} | {_count(v['comments'])} | {v['published_at'][:10]} |")
    return lines + [""]


def _my_section(result: dict) -> list[str]:
    lines = ["## Мои результаты", ""]
    if result["status"] != "ok":
        return lines + [result["note"] + ".", ""]
    lines += [(f"Канал: {_cell(result['channel_title'] or result['channel_id'])}. Роликов в данных: "
               f"{result['videos']}, медиана просмотров: {_num(result['median_views'])}. "
               "Только публичная статистика, трансляции не считаются."), ""]
    lines += _my_table("Мои лучшие ролики", result["best"])
    if result["weak"]:
        lines += _my_table("Мои слабые ролики", result["weak"])
    else:
        lines += ["Слабых роликов нет: в данных слишком мало моих роликов.", ""]
    return lines


def build_report(run: runs.Run, my_channel: str | None = None) -> str:
    """`my_channel` — id моего канала из настроек; None — канал не задан."""
    cache = Cache(run.path / "cache")
    if not cache.videos:
        raise RunError("Данных ещё нет: сначала `produce collect` или импорт из файла")
    s = summarize(run, cache)
    data = run.data
    lines = [
        f"# Отчёт: {data['month']}, {data['segment']}, v{data['version']}",
        "",
        "## Собрано",
        "",
        f"- Видео: {s.videos}",
        f"- Каналов: {s.channels}",
        f"- Квоты потрачено: {s.quota_spent} ед.",
        f"- Обращений к YouTube: {s.requests}",
        f"- Неполные данные: {s.incomplete} видео",
        "",
    ]
    skipped = data.get("incomplete_data", [])
    if skipped:
        lines += [
            "## Неполные данные",
            "",
            (f"Неполные данные: пропущено {len(skipped)} видео (недоступны, закрыты или без "
             "статистики). В выводы они не входят."),
            "",
            "Пропущенные id: " + ", ".join(f"`{i}`" for i in skipped),
            "",
        ]
    lines += _virals_section(run)
    mine = my_results.compute(cache, my_channel, data.get("source", "collect"))
    write_json_atomic(run.path / "my_results.json", mine)
    lines += _my_section(mine)
    return "\n".join(lines)


def write_report(run: runs.Run, my_channel: str | None = None) -> str:
    text = build_report(run, my_channel)
    write_text_atomic(run.path / "report.md", text)
    return text
