# MLB-011: Start/Reconcile Runtime Fixes

## Контекст

Ретроспективный execution plan для уже выполненной задачи по стабилизации `/start` и `reconcile`.

Во время ручной проверки в Docker бот успешно поднимался и восстанавливал MAX session, но:
- `/start` зависал на старте MAX client;
- создание Telegram topics падало на пустых названиях чатов;
- backfill ломался из-за несовпадения ключей сообщений;
- удаленный пользователем topic не восстанавливался при повторном `/start`;
- у бота не было зарегистрированного меню команд, и `/start` приходилось вводить руками.

## План изменений

1. [x] Исправить жизненный цикл `pymax` client в `src/infrastructure/max/adapter.py`.
2. [x] Удерживать MAX client открытым до завершения backfill в `src/application/reconcile/service.py`.
3. [x] Нормализовать названия topics и использовать fallback для пустых title.
4. [x] Привести формат сообщений MAX adapter к контракту `max_message_id`.
5. [x] Добавить диагностическое логирование по цепочке `/start -> reconcile -> create_topic -> backfill`.
6. [x] Зарегистрировать меню команд бота с `/start`.
7. [x] Реализовать восстановление удаленных Telegram topics по сохраненному mapping через probe-проверку на `/start`.
8. [x] Добавить/обновить тесты для `reconcile`, `PymaxAdapter` и startup-конфигурации команд.

## Измененные артефакты

- `src/infrastructure/max/adapter.py`
- `src/application/reconcile/service.py`
- `src/interface/telegram_handlers/handlers.py`
- `src/infrastructure/telegram/adapter.py`
- `src/application/ports/telegram_client.py`
- `src/main.py`
- `tests/application/test_reconcile.py`
- `tests/infrastructure/test_max_adapter.py`
- `tests/test_main.py`
- `AGENTS.md`

## Риски и решения

- `pymax.MaxClient.start()` оказался долгоживущим вызовом, а не коротким connect-and-return.
  Решение: запускать его в фоне и ждать `on_start` как сигнал готовности.
- Telegram Bot API отклоняет создание topic с пустым `name`.
  Решение: использовать fallback title `Chat <max_chat_id>`.
- Telegram не дает надежного пассивного сигнала об удалении topic.
  Решение: на `/start` выполнять probe в каждый сохраненный topic и пересоздавать mapping при ошибке.
- Probe-проверка topic может увеличить число запросов.
  Решение: добавлена небольшая задержка между проверками.

## Верификация

- [x] `uv run pytest tests/infrastructure/test_max_adapter.py tests/application/test_reconcile.py tests/application/test_inbound.py tests/application/test_authorization.py tests/test_main.py -q`
- [x] Ручная проверка в Docker: `/start` создает topics и выполняет backfill.
- [x] Ручная проверка в Docker: удаленный topic восстанавливается после повторного `/start`.
- [x] Ручная проверка в Telegram client: команда `/start` появилась в меню бота.

## Итог

`/start` больше не зависает на MAX client startup, корректно создает и восстанавливает topics, подтягивает backfill и имеет зарегистрированную команду в меню бота.
