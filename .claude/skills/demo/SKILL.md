---
name: demo
description: "Посмотреть проект на тестовых данных без ключа и без сети: скопировать examples/demo в data/demo и объяснить, что получилось."
---

> Только Claude Code. Необязательный бонус: те же шаги описаны в README, раздел «Демо без ключа».

1. Проверь, есть ли `data/demo` (`test -d data/demo`). Если есть, **не затирай**: спроси человека, оставить как есть, продолжить на ней или сбросить через `make reset`. Без его слова ничего не удаляй и не перезаписывай.
2. Нет: `mkdir -p data`, затем `cp -r examples/demo data/demo`.
3. Выполни по очереди и после каждой команды объясни вывод простыми словами:
   - `.venv/bin/produce --channel data/demo segments` (какие сегменты);
   - `.venv/bin/produce --channel data/demo start --segment ru --brief-lang ru`;
   - `.venv/bin/produce --channel data/demo import examples/demo/import_comments.json --segment ru` (11 видео, 2 канала, обращений к YouTube 0);
   - `.venv/bin/produce --channel data/demo virals --segment ru` (залёты и во сколько раз они выше нормы канала).
4. Скажи, что дальше можно написать «запусти месяц» на канале `data/demo`: разбор по комментариям пойдёт по `examples/demo/import_comments.json`. Ничего не публикуй, `.env` не читай.
