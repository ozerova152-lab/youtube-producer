"""Отчёт запуска `report.md`: секции добавляются по мере появления данных."""

from produce.core import runs
from produce.core.collect import Cache, summarize
from produce.core.errors import RunError
from produce.core.files import write_text_atomic


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
    return "\n".join(lines)


def write_report(run: runs.Run) -> str:
    text = build_report(run)
    write_text_atomic(run.path / "report.md", text)
    return text
