# MLB-027: Dynamic MAX video URL compatibility

## Контекст

Реальное сообщение Романа от 17.08.26 12:32 содержит корректный
`VideoAttachment(video_id=3112890335312)`. MAX отвечает на
`get_video_by_id()` payload с динамическим ключом `MP4_480`, но без поля
`cache`. Опубликованный PyMax 2.3.1 требует `VideoRequest.cache`, поэтому
Pydantic выбрасывает `ValidationError`, adapter глотает ошибку и Telegram
получает `[video]: Unsupported content`.

В upstream `main` это уже исправлено: `cache` имеет default, а лучший URL
выбирается из ключей `MP4_<quality>`. Нового PyPI-релиза после 2.3.1 пока нет.

## План изменений

1. [x] Добавить падающий regression test с реальным shape
   `{"MP4_480": "..."}` без `cache`.
2. [x] При `ValidationError` PyMax извлекать лучший `MP4_<quality>` URL из
   входного payload ошибки; остальные ошибки не маскировать молча в логах.
3. [x] Сохранить основной путь через публичный `WebClient.get_video_by_id()`.
4. [x] Обновить MAX integration contract.
5. [x] Добавить `.belief_map.sexp` и `.belief_map_cache.json` в `.gitignore`.
6. [x] Выполнить целевые тесты, `just check`, `just arch-test`, Docker build и
   `git diff --check`.
7. [x] Перенести план в `completed` и закоммитить релевантные файлы.

## Риски и открытые вопросы

- Compatibility fallback зависит от диагностического `input` Pydantic
  `ValidationError`; тест фиксирует этот контракт до выхода обновлённого PyMax.
- Выбирается максимальное положительное качество из всех `MP4_<quality>` без
  произвольного продуктового лимита.
- После обновления PyMax публичный вызов снова завершится успешно, и fallback
  автоматически перестанет использоваться.
- `local_max_test.py` остаётся локальным debug-probe и не коммитится.

## Верификация

- Regression test подтверждает выбор `MP4_480` вместо `MP4_360`.
- Существующие direct/forwarded video tests остаются зелёными.
- Полный quality gate и Docker build завершаются с кодом 0.

## Документы

- `docs/maxapi-python-contract.md`
- этот execution plan

## Результат выполнения

- Реальный MAX payload сообщения `117110862086738596` подтверждён через
  локальную сессию: `VideoAttachment`, `video_id=3112890335312`, ответ
  `MP4_480` без `cache`.
- Production adapter на этом сообщении возвращает `type=video`, непустой
  `media_url` и `file_name=video.mp4`.
- Regression test прошёл цикл red/green; MAX adapter tests: 30 passed.
- Полный pytest: 143 passed; Ruff, Pyright, architecture test, Docker build и
  diff-check завершились без ошибок.
