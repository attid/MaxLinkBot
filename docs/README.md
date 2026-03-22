# MaxLinkBot Docs

## Назначение

`docs/` хранит рабочую правду по проекту: архитектуру, контракты, execution plans и эксплуатационные инструкции для уже существующей кодовой базы.

## Порядок чтения

1. [architecture.md](/home/itolstov/Projects/other/MaxLinkBot/docs/architecture.md)
2. [golden-principles.md](/home/itolstov/Projects/other/MaxLinkBot/docs/golden-principles.md)
3. [conventions.md](/home/itolstov/Projects/other/MaxLinkBot/docs/conventions.md)
4. [glossary.md](/home/itolstov/Projects/other/MaxLinkBot/docs/glossary.md)
5. [quality-grades.md](/home/itolstov/Projects/other/MaxLinkBot/docs/quality-grades.md)
6. [configuration.md](/home/itolstov/Projects/other/MaxLinkBot/docs/configuration.md)
7. активные задачи в `docs/exec-plans/active/`

## Состав

- `exec-plans/`:
  планы выполнения: `active/` (очередь задач) и `completed/` (архив).
- `runbooks/`:
  инструкции по эксплуатации и отладке.
- `maxapi-python-contract.md`:
  зафиксированные наблюдения и ограничения интеграции с MAX WebSocket client.

## Текущая цель

Довести первую версию персонального многопользовательского Telegram-шлюза до согласованного и проверяемого состояния:
- один Telegram-бот;
- allowlist разрешенных Telegram-пользователей;
- один MAX-аккаунт на одного Telegram-пользователя;
- QR/session-based auth через `maxapi-python`;
- двусторонняя доставка сообщений между Telegram topics и личными чатами MAX;
- строгая изоляция пользовательских контекстов.
