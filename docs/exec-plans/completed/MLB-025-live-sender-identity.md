# MLB-025: Идентификация отправителя live-сообщений MAX

## Контекст

После перехода на PyMax 2.3.1 backfill корректно показывает имя и ID
отправителя, но новые сообщения из `on_message()` отображаются как
`[<numeric sender> UnknownID ...]`.

Модель `pymax.types.domain.message.Message` хранит идентификатор отправителя в
поле `sender: int | None`. History-путь уже нормализует это поле через
`_extract_sender_id()`, а live-путь читает отсутствующее `sender_id` и сохраняет
ноль.

## План изменений

1. [x] Добавить падающий тест live-сообщения PyMax 2.3.1 с числовым `sender`.
2. [x] Нормализовать sender ID и display name live-сообщений теми же методами,
   что используются для history.
3. [x] Зафиксировать подтвержденный live sender contract в документации.
4. [x] Выполнить целевой тест, `just check`, `just arch-test` и `git diff --check`.
5. [x] Перенести выполненный план в `completed` и закоммитить релевантные файлы.

## Риски и открытые вопросы

- Если display name нельзя получить из кэша или `fetch_users()`, существующий
  fallback на строковое представление sender ID сохраняется.
- Application message contract не меняется: `sender_id` остается целым числом,
  `sender_name` — строкой.
- `local_max_test.py` не относится к задаче и не коммитится.

## Верификация

- Новый тест воспроизводит `sender=192875451` без `sender_id` и ожидает
  `sender_id=192875451`, а также имя из MAX user cache.
- `uv run pytest tests/infrastructure/test_max_adapter.py -q` проходит.
- `just check`, `just arch-test` и `git diff --check` завершаются с кодом 0.

## Документы

- `docs/maxapi-python-contract.md`
- этот execution plan

## Результат выполнения

- Live callback использует `_extract_sender_id()` и `_resolve_sender_name()`,
  поэтому PyMax 2.3.1 `sender` больше не превращается в `UnknownID`.
- Regression test прошёл цикл red/green.
- MAX adapter tests: 29 passed.
- Полный pytest: 141 passed; Ruff, Pyright, architecture test и diff-check
  завершились без ошибок.
