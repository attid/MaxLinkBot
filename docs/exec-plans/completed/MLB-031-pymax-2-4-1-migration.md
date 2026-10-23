# MLB-031: PyMax 2.4.1 migration

## Контекст

`maxapi-python` запинен на 2.3.1. Вышли 2.4.0 и 2.4.1: исправлен
`VideoRequest.cache` (наш MLB-027 fallback становится ненужным), добавлены
`PollAttachment`/`Voice`/`VideoNote`, session store научился дополнять схему
существующего `session.db` (колонка `user_agent`) и восстанавливать user agent
из сессии. Решение и его последствия зафиксированы в
[ADR-0005](/home/itolstov/Projects/other/MaxLinkBot/adr/0005-pymax-2-4-1-upgrade.md).

## Границы задачи

Входит:

- поднять pin до `maxapi-python==2.4.1`, обновить `uv.lock`, синхронизировать
  окружение;
- устранить поломки, которые PyMax 2.4.1 вызывает в adapter-е и тестах;
- проверить offline-совместимость существующей сессии `session.db` (миграция
  схемы и чтение token без подключения к MAX);
- прогнать полный quality gate, arch-test и Docker build.

Не входит:

- переписывание adapter-а на новые типы (poll/voice/video note) — это отдельная
  продуктовая задача;
- удаление MLB-027 fallback до подтверждения на живом видео;
- live-проверка на реальном MAX-аккаунте (выполняется владельцем после деплоя,
  см. «Риски»).

## План изменений

1. [ ] `pyproject.toml`: `maxapi-python==2.4.1`; `uv lock` + `uv sync`.
2. [ ] Обновить adapter/тесты под изменения API 2.4.1 (типы вложений, model
   fields, import paths).
3. [ ] Offline-проверка сессии: скопировать
   `data/max_sessions/{telegram_user_id}/session.db` во временный work_dir,
   открыть `SessionStore` 2.4.1, убедиться, что token читается, а схема
   дополнилась колонкой `user_agent`.
4. [ ] Проверить, что compatibility fallback MLB-027 не ломается и остаётся
   no-op при успешном парсинге `VideoRequest`.
5. [ ] `ruff`, `pyright --strict`, `pytest`, `arch-test`, `docker build`.
6. [ ] Обновить `docs/maxapi-python-contract.md` и ADR-0004 (пометить, что
   версия обновлена ADR-0005).
7. [ ] Перенести план в `completed`.

## Риски и открытые вопросы

- **User agent**: у 2.3-сессий нет `user_agent`, PyMax сгенерирует новый. MAX
  может увидеть «новое устройство» и потребовать повторную QR-auth. Проверяется
  только на живом аккаунте, поэтому после деплоя нужно убедиться, что runtime
  восстановил сессию без `reauth_required`.
- **Shutdown (MLB-019)**: adapter отменяет `client.start()` и не вызывает
  `WebClient.close()`; в 2.4.1 `close()` реализован иначе. Нужна проверка
  остановки контейнера (нет зависания процесса).
- **Изменённый parse path**: `dispatch/mapping.py` и `dispatch/resolvers.py`
  переписаны, поэтому живой приём альбома/видео/файла проверяется на реальном
  трафике; логи `attach_count`/`media_count` из MLB-029 служат индикатором.
- Если MAX отклонит мигрированный token, штатный reauth-flow уже обрабатывает
  этот сценарий (`ApiError` на opcode LOGIN → `AuthError`).

## Верификация

- `uv pip show maxapi-python` показывает 2.4.1.
- Offline-миграция копии сессии: token читается, `PRAGMA table_info(sessions)`
  содержит `user_agent`.
- Полный `pytest` зелёный, Ruff/Pyright strict/arch-test без ошибок.
- Docker build проходит; процесс контейнера корректно останавливается.
- После деплоя: `/start` не требует reauth, живое сообщение с фото/альбомом
  приходит в Telegram, `attach_count` в логах соответствует ожидаемому.

## Документы

- [ADR-0005](/home/itolstov/Projects/other/MaxLinkBot/adr/0005-pymax-2-4-1-upgrade.md)
- `docs/maxapi-python-contract.md`
- этот execution plan

## Результат выполнения

- `pyproject.toml`: `maxapi-python==2.4.1`; `uv.lock` обновлён (46 resolved
  packages, изменился только PyMax — новых зависимостей нет, `msgpack`,
  `python-socks`, `zstandard`, `aiofiles` уже были обязательными).
- Единственная поломка в коде: compatibility fallback MLB-027 стал недостижимым,
  потому что 2.4.1 сама выбирает лучший `MP4_<quality>` URL. Fallback и helper
  `_extract_video_url_from_validation_error` удалены, вместо них добавлены тесты
  на `VideoRequest` с динамическим payload и на end-to-end резолв через модель.
- Найдено и закрыто новое отличие 2.4.1: `client.me` / `client.chats` —
  property, которые бросают `RuntimeError` до `start()`. `_current_user_id()` и
  `_invalidate_cached_chat()` терпят это состояние; добавлен regression test
  `test_get_chat_state_survives_pymax_runtime_not_started`.
- Offline-проверка сессии на копии `data/max_sessions/84131737/session.db`:
  `SessionStore.load_session()` вернул token, `device_id`, `mt_instance_id`;
  схема дополнилась nullable-колонкой `user_agent`.
- Прогон: 184 теста зелёные, Ruff/format, Pyright strict, arch-test без ошибок;
  Docker build и импорт `src.main` в образе с PyMax 2.4.1 + aiogram 3.31.0
  проходят.
- Остаётся владельцу после деплоя: убедиться, что runtime восстановил сессию без
  `reauth_required`, что живое фото/альбом приходит (`attach_count`/`media_count`
  в логах) и что контейнер останавливается без зависания (MLB-019).
