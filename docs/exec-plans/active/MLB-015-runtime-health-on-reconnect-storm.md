# MLB-015: Runtime Health On Reconnect Storm

## Контекст

Сейчас контейнер может считаться healthy, даже когда live MAX runtime фактически неработоспособен:
- `pymax` уходит в reconnect storm;
- inbound delivery перестаёт быть надёжной;
- docker healthcheck всё равно зелёный, потому что проверяет только факт запуска `python`.

Нужна связка application-runtime → health state → container healthcheck, чтобы при устойчивой деградации:
- процесс помечал себя unhealthy;
- healthcheck это видел;
- оркестратор мог перезапустить контейнер.

## План изменений

1. [x] Добавить runtime health tracker с файловым или эквивалентным состоянием.
2. [x] Зафиксировать критерий unhealthy для reconnect storm / repeated inbound failure.
3. [x] Интегрировать tracker в `BackgroundPoller` и/или inbound runtime.
4. [x] Обновить container healthcheck, чтобы он читал реальный runtime health status.
5. [x] Добавить regression tests на unhealthy transition.
6. [x] Прогнать целевые pytest-тесты.

## Риски и открытые вопросы

- Нельзя слишком агрессивно переводить runtime в unhealthy на единичном reconnect, иначе будут лишние рестарты.
- Нужно различать recoverable reconnect и storm/degraded state.
- При восстановлении runtime health status должен возвращаться в healthy автоматически.

## Верификация

- единичный reconnect не делает runtime unhealthy;
- reconnect storm переводит runtime в unhealthy;
- docker healthcheck перестаёт быть always-green и отражает состояние runtime;
- после стабилизации runtime health status восстанавливается.
