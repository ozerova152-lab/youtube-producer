---
id: T24
type: feature
origin: adhoc
phase: ''
status: done
blocked_by: []
traces_to: 01-functional-requirements.md#фичи (сбор данных) · 02-tech-architecture.md#схема-данных-файлы-вместо-таблиц · 04-user-flows.md#экраны-и-состояния (отчёт о залётах и мои результаты)
spec_sync: ok
summary: 'Ссылки на обложки залётов и моих роликов: поле thumbnail_url из уже приходящего ответа API, без новых запросов'
acceptance:
- Дано запись ответа YouTube с полем `snippet.thumbnails`; когда выполняю `collect`; тогда в `cache/videos.json` у каждого видео есть `thumbnail_url` (адрес `https://i.ytimg.com/...`, лучшее доступное качество), а число обращений и расход квоты в `run.json` такие же, как до задачи.
- Дано собранный кэш; когда выполняю `virals`; тогда у каждого залёта в `virals.json` есть `thumbnail_url`, а в `report.md` у залётов и в блоке «Мои результаты» (лучшие и слабые ролики в `my_results.json`) обложка указана ссылкой.
- 'Дано кэш старого запуска без `thumbnail_url` (создан до этой задачи); когда выполняю `virals` и `report`; тогда команды работают без ошибок, у видео поле пустое, в отчёте написано «обложка: нет данных», ничего не выдумано.'
- Дано видео, у которого API не прислал `thumbnails`; когда собираю данные; тогда `thumbnail_url` пустой, сбора это не ломает.
- Дано любая команда сбора и разбора; когда смотрю файлы запуска и логи; тогда в них только адреса обложек, картинок нет, а `git status` после запуска не показывает ни одного файла изображения.
- Дано обновлённые демо-кассеты `examples/demo/cassettes/` (скрипт `scripts/make_demo_cassettes.py` кладёт обложки в выдуманный мир); когда запускаю демо `produce --channel examples/demo`; тогда у залётов есть `thumbnail_url`, `make check` зелёный, настоящий YouTube в тестах не вызывается.
- Дано обновлённые спецификация и `docs/analytics.md`; когда читаю схему данных; тогда поле `thumbnail_url` описано там, где описаны `virals.json`, `my_results.json` и `cache/videos.json`.
verify_attempts: 2
review: human
---

## Описание

Сейчас `_video()` в `src/produce/core/youtube.py` отбрасывает `snippet.thumbnails`, хотя `videos.list` уже запрашивает `part="snippet,…"`.

Что сделать (порядок: спека, код, тесты):
- обновить `docs/spec/` (слои 1–2, `04-user-flows.md`: отчёт и «Мои результаты», обложка ссылкой) и `docs/analytics.md`;
- `youtube.py`: выбрать лучший доступный размер из `thumbnails` и сохранить как `thumbnail_url`; `virals.py` и `my_results.py` переносят поле; `report.py` показывает ссылку;
- `scripts/make_demo_cassettes.py`: добавить `thumbnails` в выдуманный мир, пересобрать кассеты и ожидаемые файлы `examples/demo/expected/`;
- старые кэши читаются без поля (как `started_on` в T23).

Ограничения: картинки не скачиваются скриптом и не попадают в git (`data/` в `.gitignore`, плюс `*.jpg`, `*.png`, `*.jpeg`, `*.webp`); данные канала остаются в `data/`; новых запросов к YouTube и лишней квоты нет; ключ, тексты комментариев и личные данные не пишутся в логи и отчёты.

Оценка: около половины рабочего дня, один присест; самый большой дифф — пересобранные демо-кассеты.

## Журнал

- 2026-11-03T00:00Z [claude] Задача заведена по просьбе человека (анализ обложек, порядок T24 → T27 → T25 → T26, хост обложек в импорте только i.ytimg.com). Сначала спецификация, потом код и сценарии, потом тесты.
- 2026-11-03T00:00Z [claude] Старт: статус in_progress, запущен implementer.
- 2026-11-03T12:00Z [implementer] Готово. Спека: поле `thumbnail_url` описано в слоях 1, 2, в 04-user-flows (экран «Залёты и мои результаты») и в `docs/analytics.md`. Код: `youtube.py` (`best_thumbnail`: maxres > standard > high > medium > default, иначе пусто), `virals.py`, `my_results.py` переносят поле (старый кэш без него даёт пусто), `report.py` пишет «[обложка](адрес)» в ячейке названия или «обложка: нет данных» (отдельную колонку не добавлял: существующие тесты считают колонки таблицы). `.gitignore`: добавлены `*.jpeg`, `*.webp`. Демо: `scripts/make_demo_cassettes.py` добавляет `thumbnails` (у demoVid_c03 нет — проверка пустого поля), кассеты пересобраны; `examples/demo/expected/` от обложек не зависит. Тесты: `tests/test_thumbnails.py` (выбор размера, сбор без новых запросов — requests_count равен числу записей кассеты, залёты и отчёт, старый кэш, нет картинок на диске). Доказано: `make check` зелёный, 1165 passed, 1 xfailed (xfail был и раньше). Настоящий YouTube не вызывался. Импорт из файла (`thumbnail_url` в CSV/JSON) не трогал: это T27.
- 2026-11-03T14:00Z [task-verifier] Круг 1. Тесты: `tests/test_thumbnails_verify.py` (20 шт., враждебные: пустой словарь/мусорные формы, нет ключа thumbnails, порядок размеров, дырявые записи, частично старый кэш, все обложки пусты, повторный отчёт, чужой хост, картинки на диске, `.gitignore`, git status). Вывод: `docs/tasks/artifacts/T24/pytest-thumbnails.txt` (30 passed вместе с тестами исполнителя), `make-check.txt` (1185 passed, 1 xfailed, ruff и gitleaks зелёные). Наблюдаемый прогон collect-virals-report на кассете: `docs/tasks/artifacts/T24/observed-demo-run.txt`.
  1. Критерий 1 (collect, thumbnail_url, обращения/квота без роста): ДОКАЗАН. maxres для роликов на 01, hqdefault для прочих. Эталон снят на коде и кассете из HEAD (git archive): requests_count=10, quota_spent=307; новый код: 10 и 307 (`run-json-counters.txt`).
  2. Критерий 2 (virals.json, report.md, my_results.json): ДОКАЗАН. У залёта и всех best/weak есть поле и «[обложка](...)» в строке отчёта.
  3. Критерий 3 (старый кэш без поля): ДОКАЗАН. Поле удалено из videos.json, virals/report с кодом 0, поле пусто, в отчёте «обложка: нет данных», ссылок нет; также частично-старый кэш.
  4. Критерий 4 (нет thumbnails): ДОКАЗАН. demoVid_c03 даёт пустую строку, сбор не ломается; пустой словарь, None, мусорные формы дают пусто.
  5. Критерий 5 (только адреса, картинок нет): ДОКАЗАН. Ни одного изображения в папке канала и в git status; `.gitignore` содержит jpg/jpeg/png/webp; ключ-канарейка в файлах запуска не найден.
  6. Критерий 6 (демо-кассеты, make check): ДОКАЗАН с оговоркой. Кассеты содержат только `https://i.ytimg.com/vi/...`, make check зелёный, сеть не вызывалась. Оговорка: голая команда `produce --channel examples/demo` только печатает «Канал: ... Сегменты», сама ничего не собирает; поток проверен через collect/virals/report на демо-кассетах.
  7. Критерий 7 (спека и analytics): ДОКАЗАН. `thumbnail_url` описан в 02-tech-architecture (строки про cache/videos.json, virals.json, my_results.json), в слое 1, в 04-user-flows и в docs/analytics.md.
  Наблюдение, не провал: `best_thumbnail` не проверяет хост — любой url из ответа API (в т.ч. `http://evil.example/...` или с пробелом/`)`) попадёт в кэш и в markdown-ссылку отчёта. Критерии этого не требуют (источник — API YouTube), тест `test_foreign_host_is_passed_as_is_documented` фиксирует поведение; если решите принимать только https://i.ytimg.com/, это отдельная правка. Для импорта (T27) проверку хоста нужно сделать обязательно.
  Вердикт: УСПЕХ, готово к приёмке человеком.
- 2026-11-03T13:00Z [implementer] Условие приёмки выполнено: `best_thumbnail` принимает адрес только если `urlparse` даёт схему https и точный хост i.ytimg.com (без логина, порта, пробелов и скобок); чужой адрес пропускается, берётся следующий размер, иначе пусто. Спека (слои 1, 2, 04-user-flows) дополнена «только https://i.ytimg.com/». Тест `test_foreign_host_is_passed_as_is_documented` заменён на `test_foreign_url_gives_empty_field` и `test_foreign_best_size_falls_back_to_next_allowed` (по просьбе человека, не ослабление). `make check` см. ниже.
- 2026-11-03T15:00Z [task-verifier] Круг 2 (проверка условия приёмки: только https://i.ytimg.com/). Тесты: новый `tests/test_thumbnails_hostile.py` (46 шт.). Вывод: `docs/tasks/artifacts/T24/round2-pytest.txt` (87 passed по трём файлам T24), `round2-make-check.txt` (1242 passed, 1 xfailed, ruff и gitleaks зелёные).
  1. Враждебные адреса: ДОКАЗАНО. 34 адреса дают пустое поле: чужой хост, http, file, javascript, data, //protocol-relative, логин (user@, user:pw@), порты :8080 и :443, i.ytimg.com.evil.example, evil.example/i.ytimg.com, x.i.ytimg.com, I.YTIMG.COM, пробел, скобки (), [], кавычки " ', обратный слэш, \n, \r\n, \t, трюки `i.ytimg.com@evil`, `evil#@i.ytimg.com`, `>`, ведущий пробел, пустая строка, без схемы; не строки (число, float, список, None, словарь, bool) дают пусто. При чужом лучшем размере берётся следующий допустимый; все плохие дают пусто.
  2. Ложные отказы: НЕТ. Проходят `…/vi/<id>/maxresdefault.jpg`, `hqdefault.jpg`, `hqdefault.jpg?v=…`, `…/vi_webp/<id>/maxresdefault.webp`, `default.jpg?sqp=…&rs=…`, id с `_` и `-`. Оговорка (не провал): заглавный хост I.YTIMG.COM отклоняется (строгое сравнение); настоящий API шлёт нижний регистр.
  3. Новые тесты исполнителя не слабее удалённого: удалённый фиксировал «пропускаем как есть», новые требуют пустое поле для 11 адресов и откат к следующему размеру (по смыслу сильнее); остальные случаи покрыл отдельным файлом выше. Подгонки под зелёное нет.
  4. Обращения и квота: ДОКАЗАНО. `test_run_json_counters_equal_old_code_baseline` (requests_count = числу записей кассеты, эталон круга 1: 10 и 307) зелёный; `make check` зелёный; изображений в git status нет.
  Вердикт: УСПЕХ, готово к приёмке человеком. Код не менялся.
- 2026-11-03T00:00Z [claude] Принято человеком с условием «закрой хост» (только https://i.ytimg.com/ для данных из API); условие выполнено, тестировщик круг 2 — успех, make check зелёный (1242 passed, 1 xfailed). Спека обновлена исполнителем (слои 1–2, 04-user-flows, analytics), spec_sync: ok. Коммит ждёт слова человека.
