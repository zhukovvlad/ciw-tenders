# 2026-06-23 — SP3: ревью/правки матчинга + запись «Статья СМР» + выгрузка .xlsx

## Что сделано

Третий под-проект модуля `estimates` — «живой документ + самовосстановление». Поверх
иммутабельного AI-снимка SP2 добавлена **ось ревью** к строке-узлу: оператор просматривает
результат матчинга, правит спорные строки (подтвердить рекомендацию / выбрать другого кандидата /
ручной подбор из справочника / забраковать), выгружает `.xlsx` с заполненной колонкой
`Статья СМР`. Заодно закрыт долг SP2 «смета залипает в `running` после жёсткого краша воркера» —
per-estimate staleness-sweep на ре-триггере. Фронт ревью/экспорта переключён с моков на реальный API.

Поток остаётся stateless по содержимому сметы: персистентен только снимок строк; ось ревью —
ещё несколько колонок на той же строке, AI-снимок неизменен.

Спек: [docs/superpowers/specs/2026-06-23-estimate-review-export-sp3-design.md](../superpowers/specs/2026-06-23-estimate-review-export-sp3-design.md).
План: [docs/superpowers/plans/2026-06-23-estimate-review-export-sp3.md](../superpowers/plans/2026-06-23-estimate-review-export-sp3.md).
Ветка `feat/estimate-review-export` (база `main`). Код-коммиты `3b3eb8c..22c62b7` (9 коммитов, 8 задач).

## Архитектура

`api → services → domain ← infrastructure`. Новые порт-методы в `domain/ports.py`, реализации в
`infrastructure/db/`, сценарии в `services/`, DTO в `api/schemas.py`. Две **независимые оси** на
строке-узле: ось AI (иммутабельна — `status`/`matched_*`/`score`/`candidates`) и ось ревью
(`review_status`/`final_*`/`reviewed_at`). Писатели осей не пересекаются: `save_node_match` трогает
только AI-снимок (и под CAS), `save_review_decision` — только ось ревью (авторитетно).

## Бэкенд

- **Миграция `0005` + ORM + домен (Task 1):** +4 колонки `estimate_rows` (`review_status` NOT NULL
  default `'unreviewed'`, `final_article_id` plain INTEGER без FK — как `matched_article_id`,
  `final_code`, `final_name`, `reviewed_at`). `ReviewStatus(StrEnum)`; `StoredEstimateRow` несёт
  снимок `candidates` + ось ревью. Накатывается на прод человеком (`just migrate`).
- **SP2-стык — защита правок (Task 2):** `fetch_matchable_nodes` дополнительно требует
  `review_status='unreviewed'`; `save_node_match` стал CAS-записью (`UPDATE ... WHERE id AND
  review_status='unreviewed'`). Гонку правка↔ре-триггер закрывает **CAS на писателе снимка**, а не
  лок на правке: тронул человек строку в окне read→write — снимок не затирает решение.
- **Чтение ревью (Task 3):** `_row_to_entity` и `get()` селектят кандидатов + ось; `EstimateRowOut`
  отдаёт `id`/`candidates`/`review_status`/`final_*`/`reviewed_at`. `source_index` наружу не отдаётся.
- **Правка решения (Task 4):** `EstimateReviewService` (чист от инфраструктуры) + `PATCH
  .../rows/{id}/review`. Матрица: `pending`→409, `confirm` без `matched_*`→422, `pick` кандидат-из-
  снимка→морозим из кандидата иначе из справочника (нет нигде→422), `reject`→`final_*`=NULL.
  `final_*` морозятся **в момент решения** (кандидат — из снимка, ручной подбор — из `template_articles`
  на момент PATCH): изменят справочник позже — решение не «поедет». Правка авторитетна (оператор
  может передумать).
- **Поиск справочника (Task 5):** `GET /articles/search` — лексический `code ILIKE %q% OR name
  ILIKE %q%`, order by code, **без** фильтра по embedding (ручному подбору вектор не нужен —
  оператор видит все статьи, включая ещё не заэмбеженные). LIKE-метасимволы экранируются;
  `len(q.strip())<2`→400 (явный guard).
- **Экспорт `.xlsx` (Task 6):** `GET /estimates/{id}/export[?strict=true]` — читает оригинал из
  MinIO, заполняет `Статья СМР`, стримит. Код пишется **только в строки-узлы** по физ.строке
  `source_index + 2` (инвариант SP1: заголовок в строке 1). Правило: `confirmed`/`overridden`→
  `final_code`; `unreviewed`+`confident`→`matched_code`; `unreviewed`+`needs_review`/`no_match`/…→
  **пусто** (сознательно не запекаем негарантированную догадку); `rejected`→пусто. `strict`→409 со
  счётчиком непросмотренных; сбой MinIO→503.
- **Staleness-sweep (Task 7):** `POST /estimates/{id}/match` перед enqueue: если `status='running'`
  и `now-updated_at > task_time_limit_s` (660s) — берёт advisory-лок как **арбитр живости** (взялся →
  прежний держатель мёртв → `running→pending`, отпустить; занят → воркер жив → no-op). Sweeper
  инъектируется (DI) и работает на **выделенном коннекте** (`bind=conn`, как Celery-обёртка
  `tasks.py`): критическая секция `try_lock → set_status(commit) → release` держит один коннект,
  иначе лок течёт (грабли SP2 на новом call-site). `detail` ре-триггера стал честным.

## Фронтенд (Task 8)

- `lib/api/estimates.ts` (новый): `getEstimate`/`patchRowReview`/`exportEstimate` + поллинг;
  `rowFromDto` маппит DTO→`MatchRow` (`id→row_number`, `name→source_name`, `code→article_code`).
  `searchArticles` в `lib/api/articles.ts`. Поток ревью/экспорта снят с моков.
- Каждое действие ревью (`confirmArbiter`/`pickCandidate`/`manualPick`/`confirmNoMatch`) коммитит на
  бэк через `patchRowReview` (маппинг действий — спека §8) и реконсилит строку из **ответа** (редьюсер
  `syncRow` + `decisionFromRow`); на ошибке PATCH — откат строки в `pending` + `toast.error` (нет
  полу-обновлённых строк). `rationale` убран из типов/UI/тестов (спека §7.1).
- `estimateId` персистится (экспорт переживает restore сессии); поиск дебаунсится 250мс + min-len 2.
- Поправлен баг поллинга: реальный `EstimateStatus` = `pending/running/ready/partial_error/blocked`
  (нет `"error"`) — поллинг резолвит на `ready`/`partial_error`, реджектит `blocked`, продолжает на
  `pending`/`running` (старый код зациклился бы на `blocked`).

## Критичные инварианты

- **Две оси не пересекаются end-to-end.** AI-снимок и ось ревью пишутся непересекающимися путями;
  экспорт читает обе, но не пишет ни в одну. Финальное ревью проследило строку match→review→
  ре-триггер→export — снимок не портится правкой и наоборот.
- **Двойная защита от гонки.** `fetch_matchable_nodes` исключает тронутые строки (read-фильтр) +
  `save_node_match` CAS (`WHERE review_status='unreviewed'`) — закрывает окно read→write даже если
  правка прилетела в процессе. Известная деградация §3.4 (pick по устаревшему кандидату молча
  деградирует в ручной-подбор, а не падает) — принята сознательно; rematch заблокирован после ревью.
- **Sweep не течёт.** `bind=conn` ⇒ `set_status`-commit не возвращает коннект в пул ⇒ `release`
  на том же коннекте; лок отпускается в `finally`. Интеграц-тест проверяет свежим probe-коннектом,
  что лок свободен после sweep.

## Верификация (выполнена)

- Бэк: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest` → **190 passed, 3 skipped**
  (1 SP2 lock-integration + 2 SP3 sweep-integration — все opt-in `RUN_LOCK_INTEGRATION=1`);
  `uv run ruff check .` чисто.
- Фронт: `cd frontend && npx vitest run` → **94 passed**; `npm run typecheck` (tsc -b strict) чисто;
  `just lint` чисто.
- Тесты не ходят в реальную БД/сеть/AI/MinIO — фейки портов + `dependency_overrides`; sweep-юнит-тест
  подменяет реальный sweeper фейк-версией на той же `_do_sweep`, корректность коннекта — в opt-in
  интеграц-тесте. Миграция `0005` накатана на Neon человеком (`just migrate`) перед мерджем.

## Процесс

План с реальным кодом на каждый шаг → subagent-driven реализация (свежий субагент на задачу,
независимое ревью spec+quality после каждой, фиксы под контролем; реализаторы в progress.md не
пишут и свои ревью не гоняют) → финальное whole-branch ревью (opus). Поймано и исправлено по ходу:
Task 8 первой попыткой отложил per-action-коммит решений на бэк (ядро SP3 §1.2) — отправлен
доделывать; там же пойман баг поллинга (`"error"`-статус, которого нет в enum; зацикливание на
`blocked`). Финальное ревью: ноль Critical/Important, все 5 межзадачных швов корректны.

## Долг / на будущее (вынесено в [TECH_DEBT](../TECH_DEBT.md))

- Нет несклип-CI-теста раунд-трипа парсер→экспортёр для стража офсета `+2` (golden-тест парсера
  `skipif` приватного файла; экспорт-тест морозит `+2` рукотворным wb, но цепочку никто не гоняет).
- Прод-код `EstimateFlow.tsx` импортит `type Progress` из `@/lib/mock/api` (связка прод↔тест-фикстура).
- `handleReview` молча no-op при `null` estimateId после оптимистичного dispatch (прикрыт регидрацией).

## Дальше

Калибровка порога 0.90 (SP3 *сохранил* провенанс правок для неё, но саму калибровку не делает);
`Статья СМР` на строках-позициях (упирается в отброшенный в SP1 снимок позиций).
