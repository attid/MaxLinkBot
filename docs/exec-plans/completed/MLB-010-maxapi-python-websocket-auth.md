# MLB-010: maxapi-python WebSocket auth — QR код через Telegram

## Статус

Ретроспективно помечено как выполненное.
QR auth через Telegram, session restore и последующая работа поверх `maxapi-python` WebSocket уже реализованы; дополнительные runtime-фиксы были оформлены отдельно.

## Контекст

При отправке телефона бот ответил "Failed to send code: WebSocket is not connected".
Выяснилось: `maxapi-python` с `device_type="WEB"` поддерживает QR код авторизацию — `client.start()` показывает QR в терминале.

## План изменений

### Auth flow: QR код вместо телефона

1. [ ] `/start` → если нет binding → создаёт MAX adapter → `start()` → получить QR картинку
2. [ ] QR картинку отправить в Telegram как фото
3. [ ] Ждать сканирования (polling клиента внутри `start()`)
4. [ ] При успехе — сохранить binding с phone из сессии (пустой или "qr_auth")
5. [ ] После авторизации — WebSocket остаётся открытым для inbound polling
6. [ ] `AuthorizationFlowService` упрощается: только `start_auth()` → QR flow
7. [ ] Телефон/SMS flow пока не нужен (QR достаточно)

### Реализация

- `MAX adapter.authenticate()` → `start()` (QR) вместо `request_code()`
- QR картинка: клиент использует `qrcode` пакет, генерит PIL Image → конвертировать в bytes → отправить в Telegram
- Inbound polling: после QR успеха WebSocket уже открыт, `_on_message` буферизирует сообщения
- `close()` корректно закрывает WebSocket

### Тесты

8. [ ] unit тесты для QR auth flow
9. [ ] `just check` проходит

### Верификация

10. [ ] Docker rebuild
11. [ ] `/start` → бот отправляет QR картинку
12. [ ] Сканирую QR → авторизация успешна
