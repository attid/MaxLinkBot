# MLB-019: PyMax shutdown race

## Контекст

Live-проверка PyMax 2.3.1 показала, что `PymaxAdapter.close()` вызывает
`WebClient.close()` параллельно с внутренним `close()` в `WebClient.start()`.
Оба coroutine закрывают один `aiosqlite` session store: в логах появляются два
`closing connection`, а процесс зависает после `connection closed`.

Воспроизведение production adapter завершается по внешнему timeout с кодом 124.

## Решение

- Если background `client.start()` task существует, adapter отменяет и ожидает
  именно ее. PyMax обрабатывает `CancelledError` и единолично закрывает runtime.
- Прямой `client.close()` используется только когда background task не создавалась.
- Локальный `local_max_test.py` использует тот же single-owner shutdown, остается
  untracked и не включается в коммиты.

## План

1. [x] Добавить regression test, запрещающий конкурентный прямой `close()` при
   запущенной client task, и увидеть ожидаемый failure.
2. [x] Минимально изменить `PymaxAdapter.close()` на cancel-and-await lifecycle.
3. [x] Прогнать adapter tests, полный pytest, Ruff, Pyright и architecture test.
4. [x] Повторить реальный adapter start/close с внешним timeout; ожидать exit 0,
   одно закрытие и `ADAPTER_CLOSED`.
5. [x] Перенести план в `docs/exec-plans/completed/`.

## Верификация

- Regression test сначала падает на старом `close()`, затем проходит.
- Live adapter subprocess завершается без timeout.
- `local_max_test.py` проходит Ruff, Pyright и compile.
- Существующая session DB остается авторизованной.

## Результат

- Regression test воспроизвел конкурентный прямой `close()` и прошел после
  перехода на cancel-and-await.
- Live adapter subprocess до исправления завершался по timeout с `exit=124` и
  двумя `closing connection`.
- После исправления тот же subprocess вывел `ADAPTER_CLOSED`, одно закрытие и
  завершился с `exit=0`.
- Полный pytest: 125 passed; измененный контур чист по Ruff/Pyright;
  architecture test прошел.
