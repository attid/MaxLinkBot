# Architecture

## Цель системы

MaxLinkBot это персональный многопользовательский шлюз между Telegram и MAX через `maxapi-python`. Один бот обслуживает нескольких разрешенных Telegram-пользователей, но каждый пользователь работает только со своей собственной MAX-сессией и своими собственными чатами.

## Зафиксированные интеграционные библиотеки

- Telegram:
  `aiogram`
- MAX:
  `maxapi-python` — WebSocket клиент с session- and QR-based auth

## Основная модель

`Telegram user -> UserBinding -> MAX session -> MAX personal chats -> Telegram topics`

Ключевое ограничение первой версии:
- только личные чаты MAX `1:1`;
- только один MAX-аккаунт на одного Telegram-пользователя;
- только личный чат пользователя с ботом;
- только SQLite;
- без синхронизации удалений и редактирований.

## Структура кода

```text
src/
  domain/
    bindings/
    chats/
    messages/
    sync/
  application/
    auth/
    reconcile/
    routing/
    polling/
  infrastructure/
    telegram/
    max/
    persistence/
    config/
    logging/
  interface/
    telegram_handlers/
    background_workers/
```

## Границы слоев

- `domain/`:
  правила привязки, состояния сессии, инварианты изоляции, модель маппинга.
- `application/`:
  сценарии `/start`, reconcile, poll, route inbound/outbound, backfill.
- `infrastructure/`:
  aiogram, `maxapi-python`, SQLite, Docker-конфигурация, адаптеры.
- `interface/`:
  команды Telegram, обработчики topic-сообщений, фоновые циклы.

## Ключевые сервисы первой версии

- `AllowlistGate`:
  мгновенно отбрасывает все входящие обновления от чужих user_id.
- `AuthorizationFlowService`:
  проводит пользователя через сценарий авторизации MAX и фиксирует binding.
- `RefreshReconcileService`:
  используется из `/start`; проверяет сессию, чаты, topics, backfill.
- `InboundSyncService`:
  переносит MAX -> Telegram.
- `OutboundSyncService`:
  переносит Telegram topic -> MAX.
- `SessionHealthService`:
  переводит binding в `reauth_required`, уведомляет пользователя и останавливает poll.

## Сущности хранения

- `telegram_users`
- `user_bindings`
- `max_chats`
- `telegram_topics`
- `message_links`
- `sync_cursors`
- `audit_events`

## Ключевой риск

Главная техническая сложность не в пересылке сообщений, а в строгом сохранении пользовательского контекста. Любой use case, poller или handler должен начинать работу с `telegram_user_id` и не иметь путей, позволяющих случайно использовать чужой binding или чужой topic mapping.
