# MLB-018: PyMax 2.3.1 migration

## Контекст

MaxLinkBot зафиксирован на `maxapi-python==1.2.5`, хотя актуальная версия библиотеки —
`2.3.1`. Новые релизы исправляют разбор неизвестных вложений, lifecycle reconnect,
очистку pending requests и декодирование новых сжатых payload.

PyMax 2.x содержит несовместимый API: `MaxClient` заменен на `WebClient`/`Client`,
конфигурация перенесена в `ExtraConfig`, handlers регистрируются декораторами,
а вложения передаются через `attachments`.

## Границы задачи

- Сохранить существующие message/routing contracts application-port.
- Добавить в MAX port явный QR lifecycle: получить QR и дождаться подтвержденной
  авторизации перед сохранением active binding.
- Перевести infrastructure adapter на `WebClient` PyMax 2.3.1.
- Сохранить QR-авторизацию, restore-only background startup и reconnect detection.
- Сохранить text/photo/file forwarding и нормализацию history/live messages.
- Не менять production-данные и `local_max_test.py`.
- Не добавлять поддержку новых MAX-функций вне существующего контракта.

## План изменений

1. [x] Зафиксировать тестами новый lifecycle API:
   - регистрация `on_start()` и `on_message()`;
   - custom QR provider возвращает QR bytes без private monkeypatch;
   - active binding сохраняется только после успешного `on_start()`;
   - `close()` останавливает background task через публичный API.
2. [x] Зафиксировать тестами новый message/file API:
   - `attachments=[Photo(...)]` и `attachments=[File(...)]`;
   - sender/chat/user поля PyMax 2.3.1 нормализуются в текущий application contract.
3. [x] Зафиксировать тестом обратимую миграцию session DB:
   - token/device_id копируются из legacy `auth` в новую `sessions`;
   - legacy `auth` остается без изменений;
   - существующая `sessions` не перезаписывается.
4. [x] Обновить `src/infrastructure/max/adapter.py` под `WebClient`, `ExtraConfig`,
   `QrHandler` и новый handler contract.
5. [x] Зафиксировать `maxapi-python==2.3.1`, обновить `uv.lock`.
6. [x] Обновить `docs/maxapi-python-contract.md` и релевантные runbooks с новым
   session/lifecycle contract.
7. [x] Прогнать adapter tests, application tests, полный pytest, Ruff, Pyright и
   architecture test.
8. [x] После выполнения перенести plan в `docs/exec-plans/completed/`.

## Риски и открытые вопросы

- Сервер может отклонить token, перенесенный из схемы 1.2.5. В этом случае binding
  должен перейти в `reauth_required`, без автоматического QR в background runtime.
- Payload-модели 2.3.1 отличаются от 1.2.5; regression tests должны сохранить
  текущую нормализацию text/media/forwarded content.
- Live-проверка реального reconnect и MAX file upload требует авторизованной сессии
  и выполняется отдельно от unit-test контура.

## Верификация

- Существующие тесты application-port и routing не требуют изменения контрактов.
- QR provider отдает PNG вызывающему Telegram handler.
- Legacy session DB мигрирует без удаления таблицы `auth`.
- `MAX -> Telegram` и `Telegram -> MAX` regression tests проходят для text/photo/file.
- `uv run pytest tests/ -q` и `just arch-test` проходят.
- Ruff/Pyright не получают новых ошибок относительно исходного baseline.

## Документы

- `docs/maxapi-python-contract.md`
- `docs/runbooks/RB-02-reauth-required.md`
- этот execution plan

## Результат выполнения

- Dependency и lock зафиксированы на `maxapi-python==2.3.1`.
- Adapter использует `WebClient`, public QR provider, decorators и public `close()`.
- QR binding сохраняется только после успешного `on_start()`.
- Legacy `auth` обратимо мигрирует в `sessions`; проверена копия реальной session DB.
- Generic MAX files получают временный URL через `get_file_by_id()`.
- Полный pytest: 125 passed; architecture test, Docker build/import smoke прошли.
- Ruff и Pyright чисты на всех измененных Python-файлах.
- Общерепозиторные Ruff/Pyright сохраняют старый baseline вне этой задачи:
  6 Ruff errors и 104 Pyright errors в неизмененных файлах.
