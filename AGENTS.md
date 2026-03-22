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
- нетривиальные изменения делать через релевантный активный plan или через новый/обновленный execution plan;
- если `AGENTS.md` отстает от `docs/`, источником правды считается `docs/`, как указано в `AI_FIRST.md`.
