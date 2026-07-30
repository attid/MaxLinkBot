# MLB-023: Commit SHA Docker-образа в startup-логах

## Контекст

Текущий Dockerfile не получает Git commit SHA, GitHub Actions не передаёт
build metadata, а startup-лог содержит только `MaxLinkBot starting...`.
По логам работающего контейнера невозможно определить, из какого commit
собран образ.

SHA нельзя надёжно вычислить внутри runtime-контейнера: `.git` не копируется
в образ. Источник правды для production build — `${{ github.sha }}` в GitHub
Actions, переданный в Docker build arg.

## План изменений

1. [x] Добавить падающий тест startup-сообщения с `git_commit_sha`.
2. [x] Добавить чтение `GIT_COMMIT_SHA` и структурированный startup-лог.
3. [x] Добавить Docker build arg/env `GIT_COMMIT_SHA` и OCI revision label.
4. [x] Передавать `${{ github.sha }}` через `docker/build-push-action`.
5. [x] Документировать startup-проверку версии образа в runbook.
6. [x] Проверить Python-код через `just check` и `just arch-test`.
7. [x] Собрать образ с тестовым SHA и проверить image env/label.
8. [x] Запустить контейнер и подтвердить SHA в startup-логе.
9. [x] После успешной проверки перенести план в completed.

## Риски и открытые вопросы

- Ручная сборка без `--build-arg GIT_COMMIT_SHA=...` должна явно показывать
  `unknown`, а не ошибочный SHA.
- SHA не является секретом и может безопасно присутствовать в image metadata
  и логах.
- Изменение workflow необходимо, иначе published GHCR image не получит SHA.
- `local_max_test.py` не относится к задаче и не изменяется.

## Верификация

- `uv run pytest tests/test_main.py -q` проверяет startup log.
- `just check` и `just arch-test` завершаются с кодом 0.
- Образ, собранный с `--build-arg GIT_COMMIT_SHA=<sha>`, содержит:
  - env `GIT_COMMIT_SHA=<sha>`;
  - label `org.opencontainers.image.revision=<sha>`.
- При запуске образа первый startup-log содержит
  `git_commit_sha=<sha>`.
- `git diff --check` завершается с кодом 0.
