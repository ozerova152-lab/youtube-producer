"""Отчёт запуска `report.md`: секции добавляются по мере появления данных."""

from produce.core import runs
from produce.core.collect import Cache, summarize
from produce.core.errors import RunError
from produce.core.files import read_json, write_text_atomic
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


def build_report(run: runs.Run) -> str:
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
    return "\n".join(lines)


def write_report(run: runs.Run) -> str:
    text = build_report(run)
    write_text_atomic(run.path / "report.md", text)
    return text
