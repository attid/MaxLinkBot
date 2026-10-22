# MLB-030: aiogram 3.31.0 upgrade

## Контекст

Проект запинен на `aiogram==3.30.0` (Bot API 10.2). На PyPI опубликован
`3.31.0` (26.08.26), который добавляет поддержку Bot API 10.3, содержит
security-обновление транзитивных зависимостей («Bump vulnerable dependencies to
patched versions»), исправление `Message.content_type` для live photos и
ускорение импорта моделей.

Обновление `maxapi-python` до 2.4.x в эту задачу **не входит**: пользователь
явно оставил PyMax на 2.3.1. Альбомный forward из MLB-029 от версии PyMax не
зависит (в 2.4.1 нет ни `album`, ни `group_id`).

Поверхность использования aiogram в проекте небольшая и стабильная:

- `Bot` методы: `send_message`, `send_photo`, `send_audio`, `send_video`,
  `send_document`, `send_media_group`, `create_forum_topic`,
  `delete_forum_topic`, `delete_message`;
- типы: `BufferedInputFile`, `InputMediaPhoto/Video/Document`, `MediaUnion`,
  `InputMediaType`, `Message`, `BotCommand`;
- инфраструктура: `Dispatcher`, `Router`, `Command`,
  `aiogram.client.session.aiohttp.AiohttpSession`,
  `aiogram.client.telegram.TelegramAPIServer`;
- исключения: `TelegramBadRequest`.

## Границы задачи

Входит:

- поднять pin `aiogram==3.31.0` в `pyproject.toml` и обновить `uv.lock`;
- прогнать полный quality gate и убедиться, что публичные контракты адаптеров
  (порт `TelegramClient`, media group, caption continuation, кастомный API base
  URL) не деградировали.

Не входит:

- обновление `maxapi-python` (остаётся 2.3.1 — отдельная задача MLB-031 при
  необходимости);
- миграция на новые возможности Bot API 10.3.

## План изменений

1. [ ] `pyproject.toml`: `aiogram==3.31.0`.
2. [ ] `uv lock` + синхронизация окружения.
3. [ ] Проверить, что используемые импорты и сигнатуры не изменились
   (`InputMedia*`, `MediaUnion`, `TelegramAPIServer`, `AiohttpSession`).
4. [ ] `ruff`, `pyright --strict`, `pytest`, `arch-test`.
5. [ ] Перенести план в `completed`.

## Риски и открытые вопросы

- Кодогенерация Bot API 10.3 могла изменить сигнатуры методов, которые мы
  вызываем (например, добавить обязательные параметры) — проверяется pyright
  strict + тестами адаптера.
- `TelegramBadRequest` остаётся тем же исключением, но текст ошибок, от которого
  зависит fallback по URL, генерируется Telegram, а не aiogram, поэтому поведение
  не меняется.
- Новых внешних зависимостей задача не добавляет, поэтому отдельный ADR не
  требуется (ADR-0002/0003 покрывают выбор библиотек).

## Верификация

- `uv pip show aiogram` показывает 3.31.0.
- Полный `pytest` (включая media group, caption continuation, кастомный API base
  URL и handlers) зелёный.
- `ruff`, `pyright` (strict), `arch-test` без ошибок.
- Docker build проходит (используется `uv sync` из lock-файла).

## Документы

- этот execution plan
- `pyproject.toml`, `uv.lock`

## Результат выполнения

- `pyproject.toml`: `aiogram==3.31.0`; `uv.lock` обновлён (46 пакетов,
  изменился только aiogram), окружение синхронизировано через `uv sync`.
- Все используемые импорты и сигнатуры на месте: `InputMediaPhoto/Video/Document`,
  `MediaUnion`, `InputMediaType`, `BufferedInputFile`, `BotCommand`, `Message`,
  `Bot`/`Dispatcher`/`Router`/`Command`, `AiohttpSession`, `TelegramAPIServer`,
  `TelegramBadRequest`.
- `maxapi-python` осознанно оставлен на 2.3.1 (вне границ этой задачи).
- Прогон: 182 теста зелёные, Ruff/format, Pyright strict и arch-test без
  ошибок; Docker build и импорт `src.main` внутри образа с aiogram 3.31.0
  проходят.
