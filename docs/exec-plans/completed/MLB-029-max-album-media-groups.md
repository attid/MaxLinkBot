# MLB-029: MAX album inbound forwarding as Telegram media groups

## Контекст

Пользователь отправляет в MAX альбом (несколько фото в одном сообщении), а в
Telegram приходит только одна картинка. Подпись при этом приходит корректно,
то есть `message.text` читается и передаётся в caption.

Причина: конвейер `MAX -> Telegram` целиком одно-медийный.

- `PymaxAdapter._extract_media_metadata()` (`src/infrastructure/max/adapter.py`)
  идёт по `message.attaches` и возвращает результат на **первом** подходящем
  вложении; последующие фото/видео отбрасываются.
- `PymaxMessage.media_url: str | None` и payload-ключи `media_url` /
  `file_name` описывают ровно одно вложение.
- `InboundSyncService._send_message_to_telegram()` и дублирующий его
  `ReconcileService._send_backfill_message()` умеют только одиночные
  `send_photo` / `send_audio` / `send_video` / `send_document`.
- В порту `TelegramClient` нет операции media group, то есть альбом технически
  нечем отправить.

Локальное воспроизведение на 3 фото-вложениях в одном сообщении:

```
attach_count_in_source = 3
delivered payload: {'max_message_id': '777', 'type': 'photo', 'media_url': 'https://a/1.jpg'}
```

MAX-сторона: библиотека `maxapi-python` собирает альбом как **одно**
сообщение с массивом вложений (`send_message(attachments=[Photo, Photo, ...])`
формирует один `MSG_SEND` фрейм), поэтому правило симметрично: N вложений в
одном сообщении на входе.

## Границы задачи

Входит:

- сбор всех вложений сообщения в список медиа-элементов (photo/video/document);
- разрешение динамических URL (file/video by id) для **каждого** элемента, а не
  только для первого;
- отправка альбома в Telegram одним media group (с чанкованием по лимиту Bot API);
- сохранение текущего поведения для одиночных вложений и для текстовых сообщений;
- единая обработка в live-пути и в backfill/reconcile-пути;
- наблюдаемость: количество вложений в логах.

Не входит:

- `Telegram -> MAX` (outbound альбомы);
- голосовые/аудио внутри альбома и прочие негруппируемые типы (для них
  сохраняется одиночный путь по первому элементу);
- изменение схемы SQLite и контракта `message_links` (одно MAX-сообщение
  по-прежнему даёт одну запись со первым Telegram message id группы).

## План изменений

1. [ ] Контракт payload: добавить ключ `media: list[{type, url, file_name}]` в
   сообщения, отдаваемые `MaxClient` (`get_messages` и
   `drain_buffered_messages`); `media_url` / `file_name` / `type` остаются как
   совместимый доступ к первому элементу.
2. [ ] `PymaxAdapter`: заменить `_extract_media_metadata` на сбор
   кандидатов-вложений с последующим разрешением URL для каждого element
   (`file_id`, `video_id`), убрать ранние `return` в
   `_resolve_document_url` / `_resolve_video_url`; добавить `media` в
   `PymaxMessage` и в `drain_buffered_messages`; логировать `attach_count`.
3. [ ] Порт `TelegramClient`: метод
   `send_media_group_to_topic(chat_id, topic_id, media, caption) -> int`
   (+ TypedDict-элемент порта). Возвращает id первого отправленного сообщения.
4. [ ] `AiogramTelegramAdapter`: реализация через `send_media_group` с
   `InputMediaPhoto` / `InputMediaVideo` / `InputMediaDocument`, чанки по 10,
   caption только на первом элементе (правило 1024 + продолжение текстом из
   MLB-024), видео/документы скачиваются как `BufferedInputFile` (URL MAX не
   годится для fetch со стороны Telegram); при невозможности подготовить группу
   — `TelegramBadRequest("failed to get HTTP URL content")`.
5. [ ] Общий хелпер `src/application/routing/media.py` с
   `collect_media_items(msg)` (выбор groupable-элементов с непустым url), чтобы
   не дублировать правило в `inbound.py` и `reconcile/service.py`.
6. [ ] `InboundSyncService._send_message_to_telegram`: при `len(items) >= 2`
   отправлять media group; при `TelegramBadRequest` с признаком недоступного
   URL — деградировать на поштучную отправку, переиспользуя существующие
   одиночные ветки (caption остаётся только на первом элементе).
7. [ ] `ReconcileService._send_backfill_message`: та же ветка, чтобы backfill
   после `/start` и `/resync` не терял фото из альбома.
8. [ ] Тесты: adapter (3 фото → 3 элемента, ordered, динамические URL для
   нескольких file/video вложений, live-буфер), telegram adapter (media group,
   чанкование >10, caption-продолжение, upload видео/документа, ошибка
   подготовки), inbound (media group вызван с 3 элементами, одиночный путь для
   одного элемента, fallback на поштучную отправку), reconcile backfill (3 фото →
   media group).
9. [ ] Обновить `docs/maxapi-python-contract.md` (альбом = одно сообщение с N
   attaches; inbound-контракт `media`).
10. [ ] `just check`, `just arch-test`; перенести план в `completed`.

## Риски и открытые вопросы

- Не подтверждено сырым payload, что MAX всегда отдаёт альбом одним сообщением
  с N attaches: в логах теперь есть `attach_count`, после раскатки это
  проверяется на реальном альбоме. Если окажется, что альбом приходит как N
  сообщений с одинаковым `max_message_id`, дедуп `exists_max_message` отбросит
  остальные — тогда потребуется отдельный follow-up план по идентичности
  альбомной группы.
- Tele групп-лимит 10 элементов, у MAX альбом может быть больше: чанкование
  внутри адаптера сохраняет порядок, id группы = id первого элемента.
- `InputMediaPhoto(media=url)` заставляет Telegram сам скачивать URL MAX (как и
  текущий `send_photo`); видео/документы скачиваются на нашей стороне, поэтому
  общий размер группы ограничен только памятью процесса.
- Негруппируемые типы в наборе (audio/voice) остаются на одиночном пути: альбом
  из смешанных типов может потерять часть вложений — осознанный scope-cut.
- Смешанный альбом photo+video после fallback отправляется по частям, поэтому
  часть сообщений придёт отдельными карточками.

## Верификация

- Regression tests: 3 фото-вложения в одном MAX-сообщении дают один
  `send_media_group_to_topic` с тремя элементами и caption с текстом и префиксом;
  одиночное фото продолжает идти через `send_photo_to_topic`.
- Тест на 12 элементов подтверждает два вызова media group по 10 и 2.
- Тест на caption > 1024 подтверждает обрезку на первом элементе и отправку
  остатка отдельным текстом.
- Тест на ошибку media group подтверждает fallback на поштучную доставку без
  потери текста.
- Backfill-тест reconcile подтверждает, что альбом из истории тоже уходит
  media group.
- Полный `just check` + `just arch-test` зелёные.

## Документы

- `docs/maxapi-python-contract.md`
- этот execution plan

## Результат выполнения

- `PymaxAdapter` собирает все рендерящиеся вложения сообщения
  (`_collect_media_candidates` + `_resolve_media_urls`) и отдаёт их через новый
  payload-ключ `media`; `media_url` / `file_name` / `type` сохранены как вид
  первого элемента, поэтому остальные потребители не менялись.
- Динамические URL (file/video by id) резолвятся для каждого вложения, а не
  только для первого.
- `TelegramClient` получил `send_media_group_to_topic`; `AiogramTelegramAdapter`
  реализует его через `sendMediaGroup` с чанкованием по 10, caption только на
  первом элементе, продолжение длинного caption — отдельным текстом,
  видео/документы загружаются как `BufferedInputFile`.
- Выбор элементов для группы вынесен в `src/application/routing/media.py` и
  используется и в live-пути (`InboundSyncService`), и в backfill-пути
  (`RefreshReconcileService`); при отказе Telegram на media group оба пути
  деградируют на поштучную доставку с сохранением caption на первом элементе.
- Наблюдаемость: лог `max buffered live message` теперь содержит
  `attach_count` и `media_count`, что позволяет отличить «одно сообщение с N
  вложениями» от «N сообщений с одинаковым id».
- Тесты: 182 passed; Ruff, Pyright (strict), architecture test — без ошибок.
- Проверено на живом аккаунте до правок: MAX присылает альбом как одно
  сообщение, Telegram получал 1 фото с корректным caption; локальное
  воспроизведение с 3 вложениями давало `media_url` только первого.
