# MLB-017: Forwarded message content from MAX

## Контекст

Пользовательский баг: пересланные сообщения из MAX могут доходить в Telegram как fallback вида
`[user]: Unsupported content`, хотя внутри forwarded payload есть поддерживаемый text/photo.

Текущее наблюдение по коду:
- `InboundSyncService` и `RefreshReconcileService` корректно рендерят text/photo/document, если адаптер отдает распознанный content;
- `PymaxAdapter` читает только верхний уровень `message.text` / `message.attaches` / `message.description`;
- в `pymax.types.Message` есть `link: MessageLink`, внутри которого есть вложенное `message`, и именно там может лежать контент forwarded/reply-like сообщений.

Нужен минимальный фикс, который сохранит текущие sender/time префиксы, но будет извлекать поддерживаемый контент из вложенного `link.message`, если верхний уровень пустой.

## План изменений

1. [x] Зафиксировать баг тестами в `tests/infrastructure/test_max_adapter.py`:
   - history/message fetch должен брать text из `message.link.message`, если верхний уровень пустой;
   - live buffered message должен брать photo/file metadata из `message.link.message`, если верхний уровень пустой.
2. [x] Прогнать таргетные тесты и убедиться, что они падают по ожидаемой причине.
3. [x] Минимально обновить `src/infrastructure/max/adapter.py`:
   - выделить helper для выбора content-source message;
   - использовать его и для history path (`get_messages`), и для live path (`_buffer_message`).
4. [x] Обновить knowledge doc `docs/maxapi-python-contract.md` новым фактом о forwarded content через `message.link.message`.
5. [x] Прогнать таргетные pytest-тесты по adapter/inbound/reconcile.

## Риски и открытые вопросы

- Нужно не потерять текущий sender/time/message-id верхнего сообщения при извлечении nested content.
- Нельзя сломать обычные text/media сообщения, где контент уже находится на верхнем уровне.
- Если nested payload бывает глубже одного уровня, текущий фикс ограничится одним уровнем `link.message`; дополнительное усложнение только при подтвержденной необходимости.

## Верификация

- Forwarded text из MAX больше не рендерится как `[user]: Unsupported content`.
- Forwarded photo/file из MAX доходит в Telegram как поддерживаемый media/document path, а не как unsupported fallback.
- Обычные не-forwarded text/photo/file сообщения продолжают проходить без регрессий.

## Итог выполнения

- `PymaxAdapter` теперь извлекает renderable content из `message.link.message`, если верхний уровень forwarded-сообщения пустой.
- Добавлены regression tests для history и live buffered paths.
- Обновлен integration knowledge doc по `maxapi-python`.
