# MLB-024: Длинные подписи Telegram media без потери текста

## Контекст

Production-лог показал `caption_len=1617` для `sendVideo`, после чего Telegram
вернул `Bad Request: message caption is too long`. Telegram Bot API ограничивает
media caption 1024 символами.

Текущий Telegram adapter также перехватывает любой exception вокруг
`bot.send_video()` как ошибку подготовки upload и подменяет исходный
`TelegramBadRequest` на `failed to get HTTP URL content`. Application принимает
эту подмену за проблему media URL и отправляет fallback, теряя исходный длинный
текст.

## План изменений

1. [x] Добавить падающий тест длинной video caption: media получает первые
   1024 символа, остаток отправляется текстом в тот же topic.
2. [x] Добавить тест разбиения очень длинного остатка по Telegram text limit.
3. [x] Добавить тест, что исходный `TelegramBadRequest` от `send_video`
   сохраняется и не маскируется.
4. [x] Реализовать общий caption split/continuation в Telegram adapter для
   photo, audio, video и document.
5. [x] Ограничить custom wrapping только ошибками подготовки/download;
   Telegram API exceptions должны проходить без подмены.
6. [x] Обновить Telegram media contract в документации.
7. [x] Выполнить `just check`, `just arch-test`, Docker build и diff-check.
8. [x] После успешной проверки перенести план в completed.

## Риски и открытые вопросы

- Telegram не предоставляет транзакцию для media + continuation messages.
  Если continuation завершится ошибкой после успешной отправки media, доставка
  считается неуспешной и будет повторена; это лучше молчаливой потери текста.
- Возвращаемым ID остаётся ID media-сообщения, чтобы существующий message link
  contract не менялся.
- Caption и continuations режутся по Python Unicode code points без потери
  исходных символов.
- `local_max_test.py` не относится к задаче и не изменяется.

## Верификация

- `uv run pytest tests/infrastructure/test_telegram_adapter.py -q` покрывает
  длинные captions и сохранение Telegram API errors.
- `just check` и `just arch-test` завершаются с кодом 0.
- Docker-образ собирается.
- `git diff --check` завершается с кодом 0.
