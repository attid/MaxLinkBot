# MLB-021: Исправление strict typing и обновление aiogram

## Контекст

Полный `uv run pyright` после изменений MLB-019/020 воспроизводимо сообщает
101 ошибку. Большинство ошибок каскадно вызвано слишком широкими аннотациями
`object` в reconcile/outbound, оставшиеся относятся к optional-полям aiogram
и тестовым mock-объектам. `uv run ruff check .` отдельно сообщает одну ошибку
сортировки импортов.

В lock-файле установлен `aiogram==3.26.0`, тогда как актуальный стабильный
релиз PyPI — `3.30.0` с поддержкой Python 3.10–3.14. Текущая версия Pyright
`1.1.408` также отстает от стабильной `1.1.411`.

## План изменений

1. [x] Уточнить доменные и async-аннотации в
   `src/application/reconcile/service.py` без изменения runtime-поведения.
2. [x] Заменить широкий return type контекста outbound на `Binding` и
   `TelegramTopic` в `src/application/routing/outbound.py`.
3. [x] Явно проверить optional-контракты aiogram в
   `src/interface/telegram_handlers/handlers.py`.
4. [x] Исправить строгие типы тестовых factory/mock/call объектов в
   `tests/application/test_health.py` и
   `tests/application/test_reconcile.py`.
5. [x] Исправить сортировку импортов в
   `src/application/health/service.py`.
6. [x] Обновить `aiogram` до `3.30.0`, Pyright до `1.1.411` и пересобрать
   `uv.lock`.
7. [x] Проверить версию aiogram, `just check`, `just arch-test`,
   `uv lock --check` и `git diff --check`.
8. [x] После успешной верификации отметить план выполненным и перенести его
   в `docs/exec-plans/completed/`.

## Риски и открытые вопросы

- Новая версия aiogram может уточнить сгенерированные Telegram Bot API типы;
  поэтому после обновления обязательны полный Pyright и все тесты.
- Сырые MAX payload остаются динамическими на инфраструктурной границе.
  Исправление должно валидировать используемые значения, а не подавлять
  диагностику Pyright.
- `local_max_test.py` остается локальным debug-probe и не изменяется.

## Верификация

- `uv run python -c "import aiogram; print(aiogram.__version__)"` печатает
  `3.30.0`.
- `uv run pyright` сообщает `0 errors`.
- `uv run ruff check .` проходит.
- `uv run pytest tests/ -q` проходит.
- `just check` и `just arch-test` завершаются с кодом 0.
- `uv lock --check` и `git diff --check` завершаются с кодом 0.
- Docker-образ `maxlinkbot:aiogram-3.30.0` собирается с production-зависимостями.
