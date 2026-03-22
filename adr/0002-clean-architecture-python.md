# 0002: Clean Architecture For MaxLinkBot

## Контекст

Проект должен поддерживать несколько активных пользователей одновременно с изоляцией данных, тестируемостью без внешних сервисов и возможностью замены инфраструктурных адаптеров (Telegram-библиотека, MAX-библиотека, БД) без переписывания бизнес-логики.

## Решение

Код организуется по принципам чистой архитектуры с направлением зависимостей только внутрь:

```
domain ← application ← infrastructure
                     ← interface
```

### Слои

- **`domain/`** — сущности, value objects, бизнес-правила. Не имеет зависимостей от других слоёв. Не знает про БД, HTTP, aiogram, maxapi.
- **`application/`** — сценарии использования (use cases). Зависит только от `domain`. Взаимодействует с внешним миром через интерфейсы (ports), определённые в `application/ports/`.
- **`infrastructure/`** — реализации портов из `application`: адаптеры aiogram, maxapi, aiosqlite, конфигурация, логирование.
- **`interface/`** — входные точки: Telegram-обработчики, background workers. Вызывают `application`, не содержат бизнес-логики.

### Подкаталоги

```
src/
  domain/
    bindings/    # Сущности и правила binding
    chats/       # MAX chats, Telegram topics
    messages/    # Message links
    sync/        # Sync cursors, audit events
  application/
    auth/        # Авторизация и binding lifecycle
    reconcile/   # RefreshReconcileService
    routing/     # Маршрутизация сообщений
    polling/     # MAX polling service
    ports/       # Интерфейсы (Repository, MaxClient, TelegramClient)
  infrastructure/
    telegram/    # aiogram-адаптер
    max/         # maxapi-адаптер
    persistence/ # aiosqlite-репозитории
    config/      # Settings из env
    logging/     # structlog-конфигурация
  interface/
    telegram_handlers/  # /start, message handlers
    background_workers/ # Poller loops
```

### Правила импортов

- `domain` не импортирует ничего из `application`, `infrastructure`, `interface`.
- `application` не импортирует ничего из `infrastructure`, `interface`.
- `infrastructure` реализует порты из `application`.
- `interface` вызывает `application`, не содержит логики.
- **Запрещены циклические зависимости.**

### Тесты

- Тесты зеркалят структуру `src/`: `tests/domain/`, `tests/application/`, etc.
- `domain`-тесты — unit, без моков инфраструктуры.
- `application`-тесты — unit с моками портов.
- `infrastructure`-тесты — integration с реальной SQLite.

## Последствия

- Все внешние библиотеки (`aiogram`, `maxapi`, `aiosqlite`) живут только в `infrastructure/`.
- Порты (`application/ports/`) — это Pydantic-модели или ABC-интерфейсы.
- Внедрение зависимостей через конструктор (DI), без глобального состояния.

## Статус

Accepted
