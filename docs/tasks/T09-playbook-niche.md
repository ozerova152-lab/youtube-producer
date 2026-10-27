---
id: T09
type: feature
status: todo
origin: spec
phase: "Разбор и стратегия"
blocked_by: [T08]
traces_to: "01-functional-requirements.md#анализ-ниши-и-конкурентов"
spec_sync: ok
summary: "Анализ ниши: сценарий агента, темы, форматы и кандидаты в конкуренты"
acceptance:
  - "Дано залёты и разбор; когда агент выполнил сценарий playbooks/04-niche.md на демо-данных; тогда niche.md содержит темы, форматы (длинные от 3 минут / Shorts) и повторяющиеся каналы, а `produce check-files` зелёный"
  - "Дано повторяющиеся каналы; когда сценарий выполнен; тогда candidates.md содержит кандидатов с причиной, а хэш settings.yaml до и после совпадает"
  - "Дано залётов нет; когда выполняется сценарий; тогда niche.md с пометкой «залётов нет», без ошибки"
verify_attempts: 0
---
## Описание

Сценарий `playbooks/04-niche.md`, шаблоны `templates/niche.md` и `templates/candidates.md`, образцы в `examples/demo/expected/`, расширение `check-files`. Кандидатов агент только предлагает, в настройки добавляет человек.

## Журнал

