# Glossary

- `Allowlist`:
  список Telegram user_id, которым разрешено пользоваться ботом.
- `Binding`:
  сохраненная связь между Telegram-пользователем и его MAX-сессией.
- `Reconcile`:
  полная сверка binding, списка MAX-чатов, topic mapping и состояния Telegram.
- `Backfill`:
  загрузка последних `N` сообщений в новый или восстановленный topic.
- `Topic Mapping`:
  стабильное соответствие `MAX chat -> Telegram topic`.
- `Session Health`:
  проверка валидности MAX-сессии и перевод в `reauth_required` при истечении.
- `Audit Event`:
  техническая запись о сбое, важном переходе состояния или служебном действии.
