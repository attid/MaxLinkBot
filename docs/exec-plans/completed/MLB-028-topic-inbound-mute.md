# MLB-028: Topic Inbound Mute

## Контекст

После отписки от MAX-канала канал исчезает из `fetch_chats()`, но сохранённый
Telegram topic остаётся в SQLite. Hourly catch-up проходит по старому mapping,
читает публичную историю канала и продолжает доставлять публикации. Перезапуск
контейнера это поведение не устраняет.

Отдельная проверка `get_chat()` показала пригодный сигнал членства:
`status='ACTIVE'` остаётся и у подписанного, и у отписанного канала, однако ID
текущего MAX-аккаунта присутствует в `participants` только у подписанного.

## Границы задачи

- Добавить `/mute` и `/unmute` для входящего направления конкретного topic.
- Сохранить исходящее направление `Telegram -> MAX` без изменений.
- Хранить mute state в SQLite и сохранять его через restart/reconcile/resync.
- Автоматически мутить канал только после явного подтверждения отсутствия
  текущего MAX ID в `participants`.
- Не удалять topics, mappings, cursors или message links.
- Не выполнять автоматический unmute.
- После ручного `/unmute` доставлять только новые сообщения без muted backlog.

## План изменений

1. [x] Добавить `inbound_enabled` в доменную модель topic, SQLite-схему и
   безопасную миграцию существующей базы.
2. [x] Расширить topic repository чтением и user-scoped обновлением inbound state.
3. [x] Добавить application service для `/mute` и `/unmute`.
4. [x] Зарегистрировать команды Telegram и сервисные ответы.
5. [x] Исключить muted topics из live, dirty, reconnect и hourly catch-up paths.
6. [x] Расширить MAX port targeted chat-state lookup и нормализацию membership.
7. [x] Добавить auto-mute подтверждённо покинутых каналов в reconcile.
8. [x] Сохранить mute state при `/resync` и не выполнять muted backfill.
9. [x] Обновить README и MAX contract.
10. [x] Выполнить TDD red/green циклы, `just check`, `just arch-test` и
    `git diff --check`.
11. [x] Перенести plan в `completed/` и закоммитить итоговый diff.

## Риски и открытые вопросы

- `Chat.status` не отражает отписку канала и не используется как сигнал.
- Отсутствие канала в одном `fetch_chats()` недостаточно для auto-mute; требуется
  успешный targeted lookup.
- Ошибка MAX API не должна менять пользовательское состояние.
- Ручной mute имеет приоритет и никогда не снимается reconcile автоматически.

## Верификация

- `/mute` внутри mapped topic отключает только inbound delivery.
- `/unmute` возвращает inbound delivery только для новых сообщений.
- Команды вне topic и в неизвестном topic дают понятный ответ.
- Muted topic не вызывает `fetch_history()` в catch-up.
- Канал без текущего MAX ID в `participants` автоматически мутится.
- Подписанный канал и неуспешный lookup сохраняют текущее состояние.
- Restart, `/start` и `/resync` не снимают mute.

## Результат

Реализованы ручные `/mute` и `/unmute`, безопасный auto-mute покинутых MAX
каналов и сохранение состояния в SQLite. После `/unmute` временная граница
отсекает накопленный backlog. Все тесты, типизация и архитектурные проверки
проходят.

## Документы

- `docs/plans/2026-08-28-topic-mute-design.md`
- `docs/maxapi-python-contract.md`
- `README.md`
- этот execution plan
