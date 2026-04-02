# MLB-016: Bidirectional File Forwarding

## Контекст

Сейчас бот умеет:
- `Telegram -> MAX` только текст и photo;
- `MAX -> Telegram` текст, photo и часть audio-path.

Обычные файлы (`document` / generic file attachments) не пересылаются как бинарные файлы:
- из Telegram topic в MAX file/document сейчас не уходит;
- из MAX в Telegram file/document сейчас рендерится максимум как placeholder или ссылка.

Нужна полноценная бинарная пересылка файлов в обе стороны для существующих topic/chat bindings.

## План изменений

1. [x] Зафиксировать текущий file contract в тестах:
   - Telegram topic `document` message должен вызывать outbound file delivery;
   - MAX inbound/history file attach должен вызывать Telegram document delivery.
2. [x] Расширить application ports:
   - `MaxClient` методами для отправки generic file/document;
   - `TelegramClient` методом для отправки document/file в topic.
3. [x] Реализовать `Telegram -> MAX` file forwarding:
   - handler скачивает `document` bytes из Telegram;
   - `OutboundSyncService` доставляет файл в MAX;
   - `PymaxAdapter` отправляет файл через `maxapi-python`, используя временный файл и attachment API.
4. [x] Реализовать `MAX -> Telegram` file forwarding:
   - `PymaxAdapter` извлекает file/document metadata и download URL из history/live message attaches;
   - `InboundSyncService` и reconcile backfill отправляют файл в Telegram как document;
   - при невозможности скачать файл используется безопасный fallback без падения всего sync.
5. [x] Обновить docs по поддержанным media/file типам и ограничениям `maxapi-python`.
6. [x] Прогнать таргетные pytest-тесты по handlers/outbound/inbound/adapter.

## Риски и открытые вопросы

- Нужно подтвердить реальный `maxapi-python` contract для generic file attachment, а не только `Photo`.
- MAX file URL может оказаться одноразовым или недоступным для прямого Telegram fetch, как уже было с частью audio URL.
- Возможно, разные file attaches (`document`, `file`, `archive`, `pdf`) будут приходить через разные payload shapes.
- Если `maxapi-python` не умеет generic file send, придётся фиксировать ограничение и выбирать fallback/альтернативный attachment path.
- Подтверждено, что self-chat `chat_id=0` может отдавать `FileAttach` только с `token/name/size` и без `url`; для таких сообщений сейчас поддерживается корректный file fallback по имени, но не бинарная пересылка файла.

## Верификация

- Telegram document, отправленный в topic, доходит в соответствующий MAX chat как файл.
- MAX file/document attachment доходит в Telegram topic как document/file, а не как placeholder.
- `/resync <chat_id>` backfill тоже пересылает file/document вложения.
- Ошибка на одном file message не валит весь sync/reconcile.
