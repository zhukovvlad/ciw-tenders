# 2026-07-01 — Золотой фонд решений (decision fund): exact-match кэш ревью-решений перед RAG

## Что сделано

Между загрузкой сметы и RAG-арбитражем добавлена стадия **`_apply_fund`**: повторяющиеся строки
решаются мгновенно, детерминированно и **без LLM** из накопленных операторских ревью-решений. Всё
новое идёт в существующий RAG-путь как раньше. Фонд — это fast-path и институциональная память, а не
замена RAG.

Ключ фонда = нормализованная крошка (`embedding_input`) — она код-free и этап-free (строится из имён,
org-предки выброшены), поэтому одна и та же работа даёт один ключ в любой смете. Якорь ответа =
`article_id` (PK каталога), без FK; живость статьи проверяется JOIN-ом в lookup.

Спек: [docs/superpowers/specs/2026-06-30-decision-fund-design.md](../superpowers/specs/2026-06-30-decision-fund-design.md) (источник правды).
План: [docs/superpowers/plans/2026-06-30-decision-fund.md](../superpowers/plans/2026-06-30-decision-fund.md) (9 задач, TDD).
Ветка `feat/decision-fund` (база `main`, merge-base `0852bad`). Поглощает паузу decision-cache-exploration
(была заблокирована багом крошко-коллизии — закрыт PR #16).

## Что именно попадает в фонд (и что НЕ попадает)

**Источник — только операторские ревью-решения**: строки, где человек подтвердил (`confirmed`) или
переопределил (`overridden`) матч через ревью-экран, с непустым `final_article_id`. Поток: смета →
RAG → оператор ревьюит → жмёт тумблер «в фонд» → `promote` пишет `(крошка → article_id)`. Фонд
наполняется **органически** из реальной ревью-работы.

- **Предикат промоушена:** `review_status ∈ {confirmed, overridden}` И НЕ (`status='matched_fund'` И
  `confirmed`). Последнее — **анти-накрутка**: фонд-хит, который человек лишь подтвердил, обратно не
  рекрутируем (новой информации нет); фонд-хит, который человек переопределил, — промоутим (реальная правка).
- **Confident-AI-догадки в фонд НЕ идут** (включая confident-but-wrong) — их кэширование размножило бы
  ошибку детерминированно.
- **Бенчмарк в фонд НЕ идёт (анти-leakage, спека §2.1):** бенчмарк — независимый held-out судья качества
  RAG; засеять фонд из него и им же мерить = 100% по построению (фиктивная метрика). `eval_matching`
  гоняет с `apply_fund=False`. Размеченная-под-бенчмарк смета дисквалифицирована как источник фонда by design.

## Архитектура

`api → services → domain ← infrastructure` — направление зависимостей без изменений.

- **Домен** ([decision_fund.py](../../backend/app/domain/decision_fund.py)): чистые
  `normalize_cache_key` (регистр+пробелы поверх org-стрипнутой крошки), `cache_key_hash` (sha256-hex —
  для unique-индекса), `resolve_fund_decision` (guard «единственный ответ»: ровно одна различная живая
  статья → она; 0 или ≥2 → None → строка идёт в RAG). `FundHit`/`FundEntry`.
  **`CRUMB_DERIVATION_VERSION`** ([classification.py](../../backend/app/domain/classification.py)) —
  единый источник правды версии крошко-деривации: и промоушен (пишет), и lookup (ищет) читают ЭТУ
  константу. Статус `EstimateRowStatus.MATCHED_FUND`.
- **БД** ([models.py](../../backend/app/infrastructure/db/models.py), ревизия
  [0007](../../backend/alembic/versions/0007_decision_fund.py)): таблица `decision_fund` (unique
  `(cache_key_hash, crumb_version, article_id)`, `article_id` без FK — зеркалит `matched_article_id`,
  `apply_plan` хард-делит статьи), колонка `estimates.is_reference`.
- **Инфра** ([decision_fund_repository.py](../../backend/app/infrastructure/db/decision_fund_repository.py)):
  `lookup` фильтрует живые статьи JOIN-ом к каталогу + по версии (код/имя оттуда же, без N+1); `upsert`
  через `on_conflict_do_update` (votes+1, source_* = последний); `clear`. Методы `EstimateRepository`:
  `set_reference`/`fetch_reference_estimate_ids`/`fetch_promotable_rows`/`fetch_pending_nodes`/`save_fund_hit`
  (CAS по `review_status='unreviewed'`, снимок без candidates/score).
- **Сервис** ([decision_fund_service.py](../../backend/app/services/decision_fund_service.py)):
  `promote`/`unreference`/`rebuild` (предикат + анти-накрутка; `is_reference` ставится только на непустом
  промоушене). Стадия `_apply_fund` в
  [estimate_matching_service.py](../../backend/app/services/estimate_matching_service.py) **перед**
  `_match_nodes`: хит → снимок `matched_fund` мимо арбитра; промах/конфликт → остаётся pending → RAG в том
  же прогоне. Условный гейт каталога (полностью-фондовая смета не ловит спурьозный `DictionaryNotReadyError`).
  Выключатель `apply_fund` через фабрику; счётчик `matched_fund` в summary.
- **API** ([routes/estimates.py](../../backend/app/api/routes/estimates.py)): `PATCH
  /estimates/{id}/reference` (двусторонний тумблер, authz владелец/админ, возвращает `promoted` count),
  `POST /estimates/fund/rebuild` (админ). `matched_fund` сериализуется в DTO строки.
- **Фронт** ([types.ts](../../frontend/src/lib/types.ts),
  [estimates.ts](../../frontend/src/lib/api/estimates.ts),
  [ReviewRow.tsx](../../frontend/src/pages/estimate/ReviewRow.tsx),
  [DoneScreen.tsx](../../frontend/src/pages/estimate/DoneScreen.tsx)): статус `matched_fund` + бейдж «из
  фонда», `setReference`/`rebuildFund`, тумблер «Эталонная смета». `reviewState` трактует `matched_fund`
  как `confident` (авто-confirm, не блокирует completion-гейт).

## Инвалидация (гибрид C)

Добавление/переименование/перекодировка статьи — фонд цел (новые хиты тянут свежее имя apply-time).
Удаление — lookup-JOIN отсекает мёртвый id лениво. Split/merge/смысл-дрейф — автодетектора в v1 нет,
бэкстопы: видимый статус «из фонда» (оператор переопределит) + админ-rebuild. Bump
`CRUMB_DERIVATION_VERSION` — старые ключи мажут мимо (безопасно, холоднее до пересборки).

## Тесты и верификация

- **Три дорожки тестов** (решение по ходу — в проекте нет инфры DB-backed юнит-тестов): (1) чистые
  доменные юниты; (2) семантика SQL-мутаций через фейки портов = зеркало SQL-контракта (как
  `test_estimate_repo_cas.py`); (3) несводимое к фейку (реальный JOIN-живость, `WHERE crumb_version`,
  `on_conflict` votes/source) — интеграционный
  [test_decision_fund_repository_integration.py](../../backend/tests/test_decision_fund_repository_integration.py)
  против выделенной тест-БД (`TEST_DATABASE_URL` из `.env`, свой engine, авто-скип при отсутствии, чистка
  в finally). Реально прогнан против тест-Neon — 3/3 green.
- Полный сьют: **бэк 351 passed / 3 skipped + ruff clean**; **фронт tsc -b + eslint + vitest 117/117 clean**.
- Миграция 0007 применена (прод-БД и тест-БД на head 0007), обратимость проверена (downgrade -1 / upgrade).

## Пост-замер ценности — ОТЛОЖЕН (осознанно)

Живой платный замер (реальная смета: пометить reference → парный прогон `apply_fund=False/True` со счётом
вызовов арбитра = реальная экономия LLM) **отложен**: в текущей БД почти нет генуинной операторской
ревью-работы (единственные confirmed/overridden — ~11 строк на одной смете, происхождение неоднозначно), а
единственная богато-размеченная смета — это бенчмарк, который в фонд идти не может (анти-leakage). Замер
data-poor и leakage-сомнителен *прямо сейчас*. Фича верифицирована без него (юниты + интеграция против
реальной тест-БД + полный сьют). Замер станет и чистым, и репрезентативным, когда накопятся реальные
операторские решения — именно то, что фонд штатно потребляет.

**Как воспроизвести замер позже** (когда есть генуинные ревью-решения на смете A и похожая смета B):
1. Отревьюить A через UI (confirm/override), тумблер «в фонд» → `promote(A)` наполняет фонд.
2. Прогнать B дважды: `build_estimate_matching_service(session, apply_fund=False)` и `=True`, посчитать
   вызовы арбитра (LLM) в каждом → разница = сэкономленные вызовы; в summary с `apply_fund=True` —
   счётчик `matched_fund`. Держать B held-out от бенчмарка.
