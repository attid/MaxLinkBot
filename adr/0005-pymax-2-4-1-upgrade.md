# 0005: PyMax 2.4.1 Upgrade

## Контекст

Репозиторий запинен на `maxapi-python==2.3.1` (ADR-0004). После 2.3.1 вышли
`2.4.0` (04.08.26) и `2.4.1` (24.08.26). Разница затрагивает ~70 файлов
пакета и включает то, что для gateway важно:

- `VideoRequest.cache` получил default и добавился валидатор выбора лучшего
  `MP4_<quality>` URL. Из-за отсутствия default в 2.3.1 adapter вынужден был
  выковыривать URL из Pydantic `ValidationError` (MLB-027) — хрупкий
  compatibility fallback до upstream-фикса.
- Новые вложения MAX: `PollAttachment`, `Voice`, `VideoNote`; у
  `UnknownAttachment` и контактных/control-вложений появились дополнительные
  необязательные поля, которые раньше терялись.
- Session store научился дополнять схему существующего `session.db`
  (`_ensure_column`, добавлена колонка `user_agent`) и восстанавливать user
  agent из сессии (`restore_user_agent_from_session`).
- Модули `pymax/fingerprint` и `pymax/versions`.

Новых зависимостей обновление не добавляет: `msgpack`, `python-socks`,
`zstandard`, `aiofiles` уже были обязательными для 2.3.1, набор пакетов в
`uv.lock` не изменился (46 resolved packages, обновился только сам PyMax).

## Решение

Поднимаем pin до `maxapi-python==2.4.1` и остаёмся на `WebClient`-API внутри
существующего adapter-контракта.

Правила миграции:
- Публичный контракт `application/ports/clients.py` не меняется.
- Все обращения к PyMax остаются в `src/infrastructure/max/adapter.py`;
  `application/` и `domain/` про библиотеку не знают.
- Compatibility fallback из MLB-027 удаляется: в 2.4.1 `VideoRequest` сам
  выбирает лучший `MP4_<quality>` URL, поэтому ветка вытаскивания URL из
  Pydantic `ValidationError` стала недостижимой. При иных сбоях lookup остаётся
  обычный лог и текстовый fallback delivery.
- `client.me` и `client.chats` в 2.4.1 стали property, которые бросают
  `RuntimeError` до `start()`; adapter обращается к ним только после старта и
  дополнительно защищён от этого состояния.
- Rollback на 2.3.1 остаётся возможным: `session.db` вперёд-совместим
  (`user_agent` — nullable колонка), legacy `auth` не удаляется.

## Последствия

- У существующих сессий нет колонки `user_agent`; PyMax дополняет схему сам
  (`_ensure_column`) и генерирует user agent, если сохранённого нет.
  Идентичность устройства для MAX определяется `device_id`, а он сохраняется в
  сессии, поэтому риск «нового устройства» ограничен сменой user agent.
  Offline-проверка на копии
  `data/max_sessions/{telegram_user_id}/session.db` подтверждена: token,
  `device_id` и `mt_instance_id` читаются, колонка `user_agent` добавляется.
- Docker-образ получает пакеты `msgpack`, `python-socks`, `zstandard`,
  `aiofiles`; размер образа немного растёт.
- Поведение inbound-парсинга сообщений (`dispatch/mapping.py`,
  `dispatch/resolvers.py`) изменилось, поэтому живой приём фото/видео/файла/
  альбома и `get_file_by_id`/`get_video_by_id` надо проверить на реальном
  аккаунте, а не только unit-тестами.
- Отдельная ручная проверка нужна для shutdown-пути (MLB-019): adapter
  отменяет `client.start()` и не вызывает `WebClient.close()`, в 2.4.1
  реализация `close()` изменена.

## Статус

Accepted
