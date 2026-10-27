"""Месячный план `plan.md`: статусы брифов, пределы из настроек, сверка плана с принятыми.

Статус брифа ставит человек (принят / отклонён / позже), агент и скрипт его не меняют. В план
идут только принятые; отклонённые и «позже» остаются файлами в `briefs/`, но в `plan.md` их нет.
Число принятых сравнивается с `publishing.min_videos_per_month` и `max_videos_per_month`; скрипт
ничего не режет и не добивает, а называет нехватку или избыток. Считаются все принятые брифы
(длинные, Shorts и посты): это то, что человек получает на месяц.
"""

import re

from produce.core import briefs as briefing
from produce.core import runs
from produce.core import strategy as strategizing
from produce.core.niche import _fields, _placeholders, _read, _split
from produce.core.settings import SettingsError

PLAN = "plan.md"
ACCEPTED, REJECTED, LATER = briefing.STATUSES
MSG_DONE = "Месяц готов. Публикацию делаете вы"

_WEEK = re.compile(r"^Неделя\s+(\d+)$")
_ITEM = re.compile(r"^-\s+Бриф\s+(\d+)\s+\(([^)]+)\):\s+«(.+)»\s+—\s+`briefs/(\d+)\.md`\s*$")


def limits_from(settings: dict) -> tuple[int, int]:
    """Минимум и максимум роликов в месяц из `publishing` в `settings.yaml`."""
    section = settings.get("publishing")
    section = section if isinstance(section, dict) else {}
    values = []
    for key in ("min_videos_per_month", "max_videos_per_month"):
        value = section.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise SettingsError(f"В settings.yaml в разделе publishing нет числа {key}. "
                                "Файл не изменён")
        values.append(value)
    if values[0] > values[1]:
        raise SettingsError("В settings.yaml publishing: минимум больше максимума. Файл не изменён")
    return values[0], values[1]


def _numbers(found: list[briefing.Brief]) -> str:
    return ", ".join(str(b.number) for b in found)


def check_decisions(found: list[briefing.Brief], minimum: int, maximum: int) -> list[str]:
    """Нет статуса, нехватка или избыток принятых; пустой список — можно собирать план."""
    empty = [b for b in found if not b.status]
    if empty:
        return [f"Нет статуса: {_numbers(empty)}"]
    accepted = sum(1 for b in found if b.status == ACCEPTED)
    if accepted < minimum:
        return [(f"Принятых {accepted}, минимум {minimum}. Нехватка: {minimum - accepted}. "
                 "План не добит. Могу сделать ещё брифы или вы смените статус «позже» на «принят»")]
    if accepted > maximum:
        return [(f"Принятых {accepted}, максимум {maximum}. Перенесите лишние в «позже» "
                 "и напишите «готово»")]
    return []


def check_plan(run: runs.Run, found: list[briefing.Brief], minimum: int, maximum: int) -> list[str]:
    """Структура `plan.md` и его состав: ровно принятые брифы, каждый один раз."""
    lines, problems = _read(run, PLAN)
    if lines is None:
        return [(f"`{PLAN}`: файла нет в {run.path}. Статусы и пределы в порядке: соберите план "
                 "из принятых брифов")]
    head, weeks = _split(lines, "##")
    head_fields = _fields(head)
    problems += _placeholders(PLAN, "вверху файла", head_fields, ["Запуск", "Принятых брифов",
                                                                  "Пределы из настроек"])
    accepted = {b.number: b for b in found if b.status == ACCEPTED}
    if head_fields.get("Принятых брифов", "").strip() not in ("", str(len(accepted))) \
            and not re.search(r"<[^>]+>", head_fields["Принятых брифов"]):
        problems.append(f"`{PLAN}`, вверху файла: «Принятых брифов» {head_fields['Принятых брифов']}, "
                        f"а принятых по статусам {len(accepted)}")
    limits = head_fields.get("Пределы из настроек", "")
    if limits and not re.search(r"<[^>]+>", limits) and limits.replace(" ", "") not in (
            f"{minimum}–{maximum}", f"{minimum}-{maximum}"):
        problems.append(f"`{PLAN}`, вверху файла: пределы «{limits}», а в `settings.yaml` "
                        f"{minimum}–{maximum}")

    if not weeks:
        problems.append(f"`{PLAN}`: нет разделов «## Неделя N»")
    seen: dict[int, int] = {}
    expected_week = 1
    for title, body in weeks:
        m = _WEEK.match(title)
        if not m:
            problems.append(f"`{PLAN}`: раздел «{title}» не распознан, нужны «Неделя 1», «Неделя 2» "
                            "и так далее")
            continue
        if int(m[1]) != expected_week:
            problems.append(f"`{PLAN}`: после «Неделя {expected_week - 1}» идёт «Неделя {m[1]}», "
                            "недели нумеруются подряд с 1")
        expected_week = int(m[1]) + 1
        items = [line for line in body if line.strip() and not line.startswith(">")]
        if not items:
            problems.append(f"`{PLAN}`, «Неделя {m[1]}»: в неделе нет брифов, пустую неделю удалите")
        for line in items:
            item = _ITEM.match(line)
            if not item:
                problems.append(f"`{PLAN}`, «Неделя {m[1]}»: строка «{line}» не разобрана, нужна "
                                "«- Бриф N (вид): «название» — `briefs/NN.md`»")
                continue
            number = int(item[1])
            seen[number] = seen.get(number, 0) + 1
            brief = next((b for b in found if b.number == number), None)
            if brief is None:
                problems.append(f"`{PLAN}`: бриф {number} в плане, а файла `briefs/{number:02d}.md` нет")
            elif brief.status != ACCEPTED:
                problems.append(f"`{PLAN}`: бриф {number} в плане, а его статус «{brief.status}»: "
                                "в план идут только принятые")
            else:
                if int(item[4]) != number:
                    problems.append(f"`{PLAN}`: у брифа {number} ссылка на `briefs/{item[4]}.md`")
                if item[2] != brief.kind or item[3] != brief.title:
                    problems.append(f"`{PLAN}`: бриф {number} записан как ({item[2]}) «{item[3]}», "
                                    f"а в файле ({brief.kind}) «{brief.title}»")
    problems += [f"`{PLAN}`: бриф {n} записан в плане {c} раза" for n, c in sorted(seen.items())
                 if c > 1]
    missing = [n for n in sorted(accepted) if n not in seen]
    if missing:
        problems.append(f"`{PLAN}`: в плане нет принятых брифов: {', '.join(map(str, missing))}")
    return problems


def check(run: runs.Run, minimum: int, maximum: int) -> tuple[list[briefing.Brief], list[str]]:
    """Шаг «план»: ворота, файлы брифов, статусы, пределы, затем `plan.md`."""
    problems = strategizing.gate(run)
    if problems:
        return [], problems
    if runs.STAGES.index(run.stage) < runs.STAGES.index(briefing.STAGE_DECISION):
        return [], ["Сначала брифы: запустите `check-files --step briefs`, потом ставьте статусы"]
    found, problems = briefing.check(run, match_strategy=False)
    if problems:
        return found, problems
    problems = check_decisions(found, minimum, maximum)
    if problems:
        return found, problems
    return found, check_plan(run, found, minimum, maximum)
