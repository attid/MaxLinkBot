# 0004: PyMax 2 Client API

## Контекст

Репозиторий использовал `maxapi-python==1.2.5` через класс `pymax.MaxClient`.
PyMax 2.x заменил этот API на отдельные `Client` и `WebClient`, публичные auth
providers, router decorators, `ExtraConfig` и новый SQLite session store.

Актуальный `maxapi-python==2.3.1` также содержит исправления reconnect lifecycle,
неизвестных вложений и сжатых TCP payload, которые важны для долгоживущего gateway.

## Решение

MaxLinkBot остается на библиотеке `maxapi-python`, но фиксирует версию `2.3.1` и
использует `pymax.WebClient`.

Правила интеграции:
- PyMax остается полностью скрыт за application-port и infrastructure adapter;
- QR URL принимается через публичный `QrHandler`, без monkeypatch private API;
- active binding сохраняется только после `on_start()`, то есть после подтверждения
  QR и сохранения token;
- live events регистрируются через `on_message()` и `on_start()`;
- отправка файлов использует `attachments=[Photo(...)]` / `attachments=[File(...)]`;
- legacy session table `auth` мигрирует в `sessions` без удаления, чтобы сохранить
  возможность rollback.

## Последствия

- Application/domain contracts не меняются.
- Старые session DB могут быть использованы после локальной обратимой миграции.
- Если MAX отклоняет перенесенный token, binding требует обычной повторной QR-auth.
- Возврат к PyMax 1.2.5 остается возможным, поскольку legacy `auth` не удаляется.
- Следующие изменения major API PyMax требуют обновления integration contract и ADR.

## Статус

Accepted
