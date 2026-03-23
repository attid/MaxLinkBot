# MLB-009: Telegram auth flow — no-commands wizard

## Статус

Ретроспективно помечено как superseded и выполненное в другой форме.
Изначальный phone/SMS wizard был заменён рабочим QR/session flow, но итоговая цель задачи — не-командный auth flow для пользователя — закрыта текущим `/start`-сценарием.

## Контекст

После миграции на `maxapi-python` (MLB-008) auth flow не был реализован. Бот отвечал "To get started, I need to link your MAX account" но не вёл пользователя дальше. Пользователь не должен помнить команды — бот должен вести через flow сам.

## План изменений

1. [x] `/start` → если нет binding → спрашивает телефон напрямую
2. [x] Телефон (`+...`) → запрашивает SMS код
3. [x] SMS код (4-6 цифр) → завершает login
4. [x] Валидация: номер телефона ≥10 символов, код 4-6 цифр
5. [x] `_pending_auth` dict в памяти (telegram_user_id → phone)
6. [x] Убрать отдельный auth.py — всё в handlers.py
7. [x] Обновить docs/configuration.md под актуальный runtime-конфиг
8. [x] `docker build` → проверка запуска

## Верификация

```bash
docker build -t maxlinkbot:test . && docker run --rm \
  -e TELEGRAM_BOT_TOKEN=... \
  -e ALLOWED_TELEGRAM_USER_IDS=... \
  -v $(pwd)/data:/data \
  maxlinkbot:test
```

Отправить `/start` → бот спрашивает телефон. Отправить `+79123456789` → бот просит код. Отправить `123456` → авторизация.
