# MLB-022: Пользовательский Telegram Bot API URL

## Контекст

Бот всегда создаёт `aiogram.Bot` со стандартной Telegram API session. Для
развёртываний через Telegram Bot API proxy нужен необязательный env-параметр
`TELEGRAM_API_URL`, например `https://api.mtlminiapps.us`.

Официальный контракт aiogram 3 предусматривает
`AiohttpSession(api=TelegramAPIServer.from_base(base_url))`.
`from_base()` нормализует завершающий `/` и формирует URL как для Bot API
методов, так и для скачивания Telegram-файлов.

## План изменений

1. [x] Добавить тест стандартного поведения без `TELEGRAM_API_URL`.
2. [x] Добавить падающий тест custom API URL, включая method/file URL.
3. [x] Добавить optional setting и тестируемую фабрику Telegram bot/session
   в `src/main.py`.
4. [x] Подключить фабрику в runtime entrypoint.
5. [x] Документировать `TELEGRAM_API_URL` в `docs/configuration.md` и
   `README.md`.
6. [x] Выполнить `just check`, `just arch-test`, Docker build и проверку diff.
7. [x] После успешной проверки перенести план в completed.

## Риски и открытые вопросы

- Пустое или состоящее из пробелов значение должно сохранять стандартный
  endpoint Telegram.
- `TelegramAPIServer.from_base()` добавляет `/bot...` и `/file/bot...`;
  поэтому env содержит только корневой URL без этих суффиксов.
- `is_local` остаётся `False`: параметр описывает HTTP API proxy, а не
  локальный файловый режим Telegram Bot API server.
- `local_max_test.py` не относится к задаче и не изменяется.

## Верификация

- `uv run pytest tests/test_main.py -q` проверяет стандартный и custom URL.
- Для `https://api.mtlminiapps.us/` method URL равен
  `https://api.mtlminiapps.us/bot{token}/{method}`, file URL —
  `https://api.mtlminiapps.us/file/bot{token}/{path}`.
- `just check` и `just arch-test` завершаются с кодом 0.
- Docker-образ собирается с новой конфигурацией.
- `git diff --check` завершается с кодом 0.
