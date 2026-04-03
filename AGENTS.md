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

Операционные факты, накопленные в последних сессиях:
- активные execution plans на текущий момент: `MLB-015-runtime-health-on-reconnect-storm.md` и `MLB-016-bidirectional-file-forwarding.md`; любые правки по health/runtime или file/media forwarding нужно соотносить именно с ними;
- runtime healthcheck больше не должен запускать Python-модуль: актуальный путь — shell script `scripts/healthcheck.sh`; если у пользователя свой `docker-compose.yml`, healthcheck нужно синхронизировать вручную;
- `local_max_test.py` используется как локальный debug-probe для `pymax`, но его нельзя коммитить;
- self-chat `chat_id=0` имеет особый media/file contract: audio/photo могут иметь прямой URL, но generic files могут приходить как `FileAttach(name, size, token)` без `url`; в таком случае текущая поддержка умеет сохранить file semantics и имя файла, но не бинарную пересылку без дополнительного token-to-download resolution;
- если из MAX приходит media с `text`/подписью, текст нельзя терять: для `photo`/`audio`/`document` он должен попадать в caption или другой явный fallback;
- repeated `Fetching history chat_id=...` раз в секунду обычно означает dirty-chat fallback после `Telegram -> MAX`, а не глобальный polling всех чатов; перед тем как считать это новой поломкой, нужно проверить dirty marker / TTL и active reply window;
- reconnect storm и stale heartbeat теперь считаются health-проблемой runtime; смотреть нужно на `src/application/health/service.py`, `src/application/routing/inbound.py`, marker `/tmp/maxlinkbot.unhealthy`, heartbeat `/tmp/maxlinkbot.heartbeat`.
