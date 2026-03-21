# MaxLinkBot V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Построить первую версию многопользовательского Telegram-шлюза к личным чатам MAX с полной изоляцией пользователей.

**Architecture:** Система строится вокруг пользовательского binding и явного topic mapping. `/start` одновременно служит входом в авторизацию и reconcile-процедурой, а фоновые pollers работают только по активным binding.

**Tech Stack:** Python, aiogram, Docker, SQLite, Pumax, `love-apples/maxapi`.

---

## Последовательность выполнения

1. Сначала зафиксировать репозиторный каркас, конфиг и контракт интеграций.
2. Затем реализовать доменную модель и SQLite-схему.
3. После этого сделать сценарий авторизации и состояния binding.
4. Потом собрать `/start` + reconcile + topic recovery.
5. Затем реализовать двустороннюю маршрутизацию и фоновые pollers.
6. В конце закрыть Docker-операционку, runbooks и hardening.

## Активные execution plans

- `MLB-001`:
  базовый каркас проекта и проектные контракты.
- `MLB-002`:
  доменная модель, схема SQLite и репозитории.
- `MLB-003`:
  сценарий авторизации MAX и жизненный цикл binding.
- `MLB-004`:
  `/start` как refresh/reconcile и восстановление topics.
- `MLB-005`:
  MAX -> Telegram доставка и backfill.
- `MLB-006`:
  Telegram -> MAX доставка и защита main chat.
- `MLB-007`:
  фоновые проверки, `reauth_required`, аудит событий.
- `MLB-008`:
  Docker, конфиг, runbooks, приемочные проверки.

## Обязательные сквозные требования

- строгий allowlist до входа в бизнес-логику;
- доказуемая изоляция пользовательских контекстов;
- отсутствие молчаливой потери неподдерживаемых вложений;
- документирование всех архитектурных решений, которые выходят за рамки текущего ТЗ.
