# MLB-013: Event-Driven Inbound Sync With Hourly Catch-Up

## Контекст

Текущая доставка `MAX -> Telegram` опирается на регулярный polling `fetch_history()` по всем чатам каждого активного binding.
Это создаёт лишнюю нагрузку и плохо масштабируется:
- при десятках и сотнях чатов бот будет регулярно делать много запросов истории;
- пользователь уже подтвердил, что `pymax` умеет live message handlers (`on_message`-style), то есть постоянный polling history не нужен как основной канал;
- polling стоит оставить только как страховочный catch-up после рестартов, пропущенных событий и временных сбоев сокета.

Нужно перевести inbound delivery на модель:
- live messages приходят через WebSocket message handler;
- приложение держит долгоживущий inbound MAX client на binding;
- fallback catch-up по cursor выполняется редко, раз в час;
- `/start` и `/resync` остаются механизмами reconcile / topic rebuild, а не основным транспортом новых сообщений.

## План изменений

1. [ ] Зафиксировать новый runtime-контракт inbound sync:
   live delivery через message handler, catch-up polling только как fallback.
2. [ ] Расширить MAX client port минимальным API для чтения buffered live messages из долгоживущего adapter.
3. [ ] Обновить `PymaxAdapter`, чтобы он:
   - накапливал live messages в буфере;
   - отдавал их через явный `drain_*` метод;
   - сохранял достаточные поля сообщения для Telegram rendering и cursor update.
4. [ ] Переписать `InboundSyncService` на долгоживущую модель:
   - один живой MAX client на binding;
   - `ensure_started()` / lazy start;
   - отдельный путь обработки live buffered messages без `fetch_history()` по всем чатам на каждом цикле.
5. [ ] Добавить explicit catch-up path для existing topics:
   редкий проход по cursor/history для already-known chats, без постоянного minute-by-minute polling.
6. [ ] Обновить `BackgroundPoller`:
   - frequent lightweight loop только для draining live buffers;
   - health check и catch-up/reconcile по расписанию с отдельным редким интервалом;
   - reuse `InboundSyncService` instances между тиками вместо создания нового service/client каждый раз.
7. [ ] Решить обнаружение новых MAX chats:
   использовать редкий `reconcile` как discovery-механизм для missing topics, чтобы не делать `fetch_chats()` на каждом live-цикле.
8. [ ] Добавить/обновить unit tests:
   - live buffered messages deliver without history polling;
   - hourly catch-up still fetches missed messages by cursor;
   - background poller reuses inbound service/client and does not hit history on every tick.
9. [ ] Обновить docs/контракт `pymax`, если новая модель подтвердит дополнительные инварианты.
10. [ ] Прогнать релевантный pytest suite и ручную проверку в Docker.
11. [ ] Защитить startup/runtime от удалённой on-disk MAX session:
    background `start()` должен падать контролируемым `AuthError`, а не уходить в QR login flow.

## Риски и открытые вопросы

- Нужно не допустить двойной доставки одного и того же MAX message между live buffer и hourly catch-up.
- Нельзя потерять buffered messages при stop/restart между моментом получения и моментом доставки.
- Нужно аккуратно закрывать долгоживущие MAX clients при shutdown и при переходе binding в `reauth_required`.
- Редкий `reconcile` как discovery-механизм означает, что новый MAX chat может появиться в Telegram не мгновенно, а с задержкой до catch-up интервала; это допустимый компромисс ради снижения нагрузки.
- Удаление `MAX_WORK_DIR/{telegram_user_id}/session.db` при `ACTIVE binding` не должно запускать QR flow в background-путях; нужен явный stale-session guard.

## Верификация

- новые сообщения из MAX доставляются в Telegram без minute-by-minute `fetch_history()` по всем чатам;
- в steady-state лог показывает live processing, а history polling выполняется только на редком catch-up;
- после рестарта или временного сбоя missed messages дочитываются hourly catch-up path по cursor;
- existing tests на reconcile/outbound/inbound не ломаются;
- релевантный pytest suite проходит;
- ручная проверка в Docker подтверждает realtime delivery reply из MAX в Telegram topic.
