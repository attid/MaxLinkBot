# MaxLinkBot Docs

## Назначение

`docs/` хранит всю рабочую правду по проекту до появления кода и после него.

## Порядок чтения

1. [architecture.md](/home/itolstov/Projects/other/MaxLinkBot/docs/architecture.md)
2. [golden-principles.md](/home/itolstov/Projects/other/MaxLinkBot/docs/golden-principles.md)
3. [conventions.md](/home/itolstov/Projects/other/MaxLinkBot/docs/conventions.md)
4. [glossary.md](/home/itolstov/Projects/other/MaxLinkBot/docs/glossary.md)
5. [quality-grades.md](/home/itolstov/Projects/other/MaxLinkBot/docs/quality-grades.md)
6. активные задачи в `docs/exec-plans/active/`

## Состав

- `plans/`:
  мастер-план первой версии и большие проектные документы.
- `exec-plans/active/`:
  очереди задач для реализации.
- `exec-plans/completed/`:
  архив завершенных задач.
- `runbooks/`:
  будущие инструкции по эксплуатации и отладке.

## Текущая цель

Подготовить первую версию персонального многопользовательского Telegram-шлюза к реализации:
- один Telegram-бот;
- allowlist разрешенных Telegram-пользователей;
- один MAX-аккаунт на одного Telegram-пользователя;
- двусторонняя доставка сообщений между Telegram topics и личными чатами MAX;
- строгая изоляция пользовательских контекстов.
