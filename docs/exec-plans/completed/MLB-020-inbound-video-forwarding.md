# MLB-020: Inbound video forwarding

## Контекст

Live-проверка self-chat `chat_id=0` на PyMax 2.3.1 обнаружила два видео:

- direct `VideoAttachment`, 1280×720, 842 секунды, 196464264 bytes;
- forwarded видеокружок внутри dict-shaped `link.message`, 480×480, 18 секунд,
  1215665 bytes.

Оба URL успешно резолвятся через `WebClient.get_video_by_id()` по ID верхнего
сообщения. Текущий adapter возвращает оба сообщения как `type=user` без URL,
поскольку ожидает `attach.url` и object-shaped `link.message`.

Aiogram 3.26 / Telegram Bot API принимает MPEG4 через `sendVideo`, но документирует
лимит 50 MB для bot video upload.

## Решение

- Нормализовать object-shaped и dict-shaped `link.message`.
- Сохранять ID верхнего сообщения для `get_video_by_id(chat_id, message_id, video_id)`.
- Возвращать из MAX adapter `type=video`, URL и имя `video.mp4`.
- Добавить `send_video_to_topic()` в Telegram port и adapter.
- Перед скачиванием видео делать Range-пробу размера с теми же header profiles:
  - до 50 MB — скачать и отправить `BufferedInputFile`, `supports_streaming=True`;
  - больше 50 MB или при ошибке подготовки — вернуть контролируемый
    `TelegramBadRequest`, чтобы inbound routing отправил `[video]: URL`.

## План

1. [x] RED: adapter tests для direct `VideoAttachment` и dict-shaped forwarded
   видеокружка с `get_video_by_id()`.
2. [x] GREEN: нормализовать dict link и резолвить video URL.
3. [x] RED: routing test для `send_video_to_topic()` и URL fallback.
4. [x] GREEN: добавить video branch в inbound routing и Telegram port.
5. [x] RED: Telegram adapter tests для small video upload и >50 MB rejection.
6. [x] GREEN: реализовать Range size probe, download/upload и limit guard.
7. [x] Обновить integration contract и прогнать полный verification gate.
8. [x] Live-проверка двух реальных self-chat сообщений через production adapter.
9. [x] Перенести plan в `docs/exec-plans/completed/`.

## Верификация

- Direct и forwarded video получают `type=video` и реальный URL.
- Видеокружок 1.2 MB проходит small-video upload preparation.
- Видео 196 MB не скачивается целиком и уходит в явный URL fallback.
- Caption не теряется.
- Полный pytest, изменённые Ruff/Pyright и architecture test проходят.

## Результат

- Direct 196464264-byte video и forwarded 1215665-byte видеокружок подтверждены
  на реальной self-chat history через production adapter.
- Оба сообщения нормализуются как `type=video`, получают URL через
  `get_video_by_id()` и сохраняют top-level message ID.
- Видеокружок полностью скачан и подготовлен как 1215665-byte
  `BufferedInputFile`.
- Большое видео остановлено Range preflight до полного скачивания и переведено
  в `[video]: URL` fallback.
- Полный pytest: 133 passed; Ruff изменённого контура, architecture test,
  Docker build и diff-check прошли.
- Pyright чист для video adapter/routing/Telegram файлов; общие старые ошибки
  `reconcile/service.py` и `test_reconcile.py` остались без новых регрессий.
