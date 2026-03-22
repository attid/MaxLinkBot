# Agent Entry Point

Этот репозиторий уже содержит код, тесты и набор проектных документов.
`docs/` остается источником правды для архитектуры, контрактов и execution plans.

Источник правил для агента сейчас:
- [AI_FIRST.md](/home/itolstov/Projects/other/MaxLinkBot/AI_FIRST.md)
- [docs/README.md](/home/itolstov/Projects/other/MaxLinkBot/docs/README.md)

Порядок чтения перед любой реализацией:
1. `AI_FIRST.md`
2. `docs/README.md`
3. профильные документы из `docs/`
4. активный план из `docs/exec-plans/active/`
5. `README.md`, если задача затрагивает запуск, конфиг или локальную разработку
6. ADR из `adr/`, если задача меняет архитектуру

Текущее состояние:
- в репозитории есть рабочий Python-код, тесты, Docker-конфигурация и execution plans;
- изменения в коде нужно соотносить с актуальными документами в `docs/`;
- любые правки кода и поведения разрешены только если задача уже зафиксирована в `docs/`:
  либо через релевантный активный plan в `docs/exec-plans/active/`, либо через новый/обновленный execution plan, созданный до начала изменений;
- если в `docs/` нет зафиксированной задачи, агент не должен менять код, тесты или runtime-конфигурацию до появления такого документа;
- если `AGENTS.md` отстает от `docs/`, источником правды считается `docs/`, как указано в `AI_FIRST.md`.

Важные наблюдения из последних отладок:
- не опираться на старое предположение, что Telegram topics недоступны в private chat: в актуальном Telegram Bot API и новых версиях `aiogram` `createForumTopic` и отправка в topic private-чата поддерживаются;
- сценарий `/start` должен не только создать topic mapping, но и сразу выполнить backfill последних `N` сообщений;
- критичный инвариант для `RefreshReconcileService`: MAX client нельзя закрывать до завершения backfill и сохранения sync cursor для новых topics;
- при расследовании проблем `/start`, reconcile и topic creation сначала проверять `src/application/reconcile/service.py`, `src/interface/telegram_handlers/handlers.py` и runbook `docs/runbooks/RB-04-topic-creation.md`;
- логи вида `pymax.core: Client starting` сами по себе не указывают на причину бага: для root cause нужно отдельно проверять жизненный цикл клиента и фактическое выполнение backfill после `list_personal_chats()`.
