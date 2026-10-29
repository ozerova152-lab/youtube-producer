"""История запусков: что уже предлагали и отклоняли, и возврат брифов «позже».

История берётся только из запусков того же сегмента (ru и en не смешиваются); учитываются
все версии (v1 и v2 одного месяца), кроме текущего запуска и более новых. Старые запуски
скрипт только читает, не меняет. Совпадение тем — сигнализация, а не решение: сравниваются
значимые слова названий (без служебных слов, по началу слова, чтобы «нейросеть» и «нейросети»
совпали) и видео-основа брифа. Синонимов скрипт не знает: решает человек.
Вернуть отклонённую тему можно только руками, сменив статус в старом брифе.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from produce.core import briefs as briefing
from produce.core import runs, strategy
from produce.core.errors import RunError
from produce.core.files import write_text_atomic
from produce.core.niche import _fields, _read, _split
from produce.core.text import plural

REJECTED = "отклонён"
LATER = "позже"
RETURNED_FIELD = "Возвращён из"
MSG_NO_RUNS = "Прошлых запусков нет"

_RETURNED = re.compile(r"^(\S+?),\s*бриф\s+(\d+)\s*$")
_WORD = re.compile(r"[a-zа-яё0-9]+")
_STATUS_LINE = re.compile(r"^(-\s+Статус\s*:).*$", re.MULTILINE)
_TITLE_NUMBER = re.compile(r"^(#\s+Бриф\s+)\d+", re.MULTILINE)
_RUN_LINE = re.compile(r"^(-\s+Запуск\s*:).*$", re.MULTILINE)
_STOP_WORDS = """
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне
было вот от меня еще нет о из ему теперь когда даже ну ли если уже или ни быть был него до вас
там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без
будто чего раз тоже себе под будет тогда кто этот того потому этого какой совсем ним здесь этом
один почти мой тем чтобы нее сейчас были куда зачем всех можно при два об другой после над
больше тот через эти нас про всего них какая много три эту моя свою этой перед том такой им
the a an and or of to for in on with without how why what your you my is are be it this that
from by at as vs
"""
_STOP = frozenset(_STOP_WORDS.split())
SHARE = 2 / 3  # доля слов более короткого названия, которая должна совпасть
MIN_SHARED = 2
SAME_SOURCE_SHARE = 0.4  # у тех же видео-основы хватает одного общего слова, но не «нейросеть» на пять слов


@dataclass
class PastBrief:
    """Бриф прошлого запуска, прочитанный без проверки структуры."""

    run: str  # имя папки запуска
    month: str
    number: int
    title: str
    kind: str
    status: str
    base: str
    returned_from: tuple[str, int] | None
    path: Path

    @property
    def rel(self) -> str:
        return f"{self.run}/{briefing.BRIEFS_DIR}/{self.path.name}"


def stems(text: str) -> set[str]:
    """Значимые слова текста в нормальной форме: без служебных слов, по началу слова."""
    result = set()
    for word in _WORD.findall(text.lower().replace("ё", "е")):
        if len(word) < 3 or word in _STOP:
            continue
        cyrillic = re.match(r"[а-я]", word) is not None
        result.add(word[: 6 if cyrillic else 5])
    return result


def similar(a: set[str], b: set[str]) -> bool:
    """Темы похожи: общих значимых слов не меньше двух и две трети слов короткого названия."""
    shared = len(a & b)
    return shared >= MIN_SHARED and shared / min(len(a), len(b)) >= SHARE


def same_source_topic(a: set[str], b: set[str]) -> bool:
    """Для брифов на одном видео-источнике планка ниже: одно общее слово и две пятых названия."""
    shared = len(a & b)
    return shared >= 1 and shared / min(len(a), len(b)) >= SAME_SOURCE_SHARE


def _read_brief(run_name: str, month: str, path: Path) -> PastBrief | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    head, _ = _split(lines, "##")
    title = next((m[2].strip() for m in map(briefing._TITLE.match, head) if m), "")
    if not title:
        return None
    status = next((m[1].strip() for m in map(briefing._STATUS_LINE.match, head) if m), "")
    fields = _fields(lines)
    head_fields = _fields(head)
    returned = _RETURNED.match(head_fields.get(RETURNED_FIELD, ""))
    return PastBrief(run_name, month, int(path.stem), title, head_fields.get("Вид", ""), status,
                     fields.get("Залёт", "").strip("` "),
                     (returned[1], int(returned[2])) if returned else None, path)


def _briefs_of(run_dir: Path, month: str) -> list[PastBrief]:
    folder = run_dir / briefing.BRIEFS_DIR
    if not folder.is_dir():
        return []
    found = [_read_brief(run_dir.name, month, p) for p in sorted(folder.glob("*.md"))
             if briefing._FILE.match(p.name)]
    return [b for b in found if b]


def _key(run: runs.Run) -> tuple[str, int]:
    return str(run.data["month"]), int(run.data["version"])


def past_dirs(channel: Path, segment: str, current: runs.Run | None) -> list[tuple[str, int, Path]]:
    """Запуски сегмента, предшествующие текущему (текущий и более новые не входят)."""
    dirs = runs.segment_run_dirs(channel, segment)
    if current is None:
        return dirs
    return [d for d in dirs if (d[0], d[1]) < _key(current)]


def past_briefs(channel: Path, segment: str, current: runs.Run | None) -> list[PastBrief]:
    return [b for month, _, path in past_dirs(channel, segment, current)
            for b in _briefs_of(path, month)]


def _returned_sources(channel: Path, segment: str) -> set[tuple[str, int]]:
    """Брифы «позже», уже возвращённые в какой-либо запуск сегмента."""
    return {b.returned_from for month, _, path in runs.segment_run_dirs(channel, segment)
            for b in _briefs_of(path, month) if b.returned_from}


@dataclass
class Overview:
    runs_count: int
    rejected: list[PastBrief]
    proposed: list[PastBrief]
    later: list[PastBrief]


def overview(channel: Path, segment: str, current: runs.Run | None) -> Overview:
    """Что было в прошлых запусках: отклонённые, остальные предложенные и «позже» к возврату."""
    dirs = past_dirs(channel, segment, current)
    found = [b for month, _, path in dirs for b in _briefs_of(path, month)]
    returned = _returned_sources(channel, segment)
    later = [b for b in found if b.status == LATER and (b.run, b.number) not in returned]
    # Возвращённая копия не считается новой темой: она та же, что исходный бриф.
    proposed = [b for b in found if b.status != REJECTED and not b.returned_from]
    return Overview(len(dirs), [b for b in found if b.status == REJECTED], proposed, later)


def summary(channel: Path, segment: str, current: runs.Run | None) -> str:
    """Строка экрана «Что уже было»."""
    info = overview(channel, segment, current)
    if not info.runs_count:
        return MSG_NO_RUNS
    n = len(info.rejected)
    word = plural(n, "тема", "темы", "тем")
    return (f"Отклонено в прошлых запусках: {n} {word}. Брифов «{LATER}»: {len(info.later)}. "
            "Вернуть?")


def _rejected_message(old: PastBrief) -> str:
    return f"Тема «{old.title}» отклонена в {old.month} (бриф `{old.rel}`). Замените её"


def _proposed_message(old: PastBrief) -> str:
    status = old.status or "без статуса"
    hint = (f" Она в «{LATER}»: верните её командой `produce later`, а не пишите заново."
            if old.status == LATER else " Замените её")
    return (f"Тема «{old.title}» уже предлагалась в {old.month} (бриф `{old.rel}`, "
            f"статус «{status}»).{hint}")


def brief_repeats(channel: Path, run: runs.Run) -> list[str]:
    """Повторы тем в брифах текущего запуска: отклонённые и уже предложенные раньше."""
    segment = str(run.data["segment"])
    old = past_briefs(channel, segment, run)
    if not old:
        return []
    problems: list[str] = []
    for new in _briefs_of(run.path, str(run.data["month"])):
        mine = stems(new.title)
        found = []
        for o in old:
            if new.returned_from == (o.run, o.number):
                continue  # это возвращённая копия, а не повтор
            if o.status == REJECTED:
                theirs = stems(o.title)
                if similar(mine, theirs) or (
                        new.base and new.base == o.base and same_source_topic(mine, theirs)):
                    found.append((0, o))
            elif similar(mine, stems(o.title)):
                found.append((1, o))
        if found:
            _, first = min(found, key=lambda x: x[0])
            text = _rejected_message(first) if first.status == REJECTED else _proposed_message(first)
            problems.append(f"{text.rstrip('.')}. Найдено: `{briefing.BRIEFS_DIR}/{new.path.name}`")
    return problems


def strategy_repeats(channel: Path, run: runs.Run) -> list[str]:
    """Отклонённая тема в тексте стратегии: слова названия отклонённого брифа в одной строке.

    Файла нет или он не читается — повторов нет: об этом скажет проверка самой стратегии.
    """
    lines, _ = _read(run, strategy.STRATEGY)
    if lines is None:
        return []
    old = [o for o in past_briefs(channel, str(run.data["segment"]), run) if o.status == REJECTED]
    problems, seen = [], set()
    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.startswith(("#", ">")):
            continue
        words = stems(line)
        for o in old:
            title = stems(o.title)
            if (o.rel in seen or len(title) < MIN_SHARED
                    or len(title & words) / len(title) < SHARE):
                continue
            seen.add(o.rel)
            problems.append(f"{_rejected_message(o)}. Найдено: `strategy.md`, строка {number}")
    return problems


def _next_number(folder: Path) -> int:
    numbers = [int(p.stem) for p in folder.glob("*.md") if briefing._FILE.match(p.name)]
    return max(numbers, default=0) + 1


def _append_to_line(pattern: re.Pattern, text: str, tail: str) -> str:
    """Оставляет в первой найденной строке только имя поля и дописывает `tail`."""
    return pattern.sub(lambda m: m[1] + tail, text, count=1)


def return_briefs(run: runs.Run, picks: list[PastBrief]) -> list[tuple[PastBrief, Path]]:
    """Копирует выбранные брифы «позже» в запуск: статус пустой, источник записан в шапке.

    Исходные файлы не меняются. Ссылки на залёты в копии остаются как были: если их нет
    в `virals.json` нового запуска, проверка брифов это покажет и агент перепривяжет бриф.
    """
    folder = run.path / briefing.BRIEFS_DIR
    done = []
    for old in picks:
        text = old.path.read_text(encoding="utf-8")
        mark = f"\n- {RETURNED_FIELD}: {old.run}, бриф {old.number:02d}"
        where = f" {run.data['month']}, сегмент {run.data['segment']}"
        text = _append_to_line(_STATUS_LINE, text, mark)
        text = _append_to_line(_RUN_LINE, text, where)
        number = _next_number(folder)
        # Номер в заголовке должен совпасть с именем файла, иначе проверка брифов откажет.
        text = _TITLE_NUMBER.sub(rf"\g<1>{number}", text, count=1)
        target = folder / f"{number:02d}.md"
        write_text_atomic(target, text)
        done.append((old, target))
    return done


def require_run(channel: Path, segment: str, month: str) -> runs.Run:
    found = runs.list_runs(channel, month, segment)
    if not found:
        raise RunError(f"Запуска для сегмента {segment} за {month} ещё нет: сначала `produce start`")
    return found[-1]
