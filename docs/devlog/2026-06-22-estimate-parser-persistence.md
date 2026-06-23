# 2026-06-22 — SP1: загрузка сметы + иерархический парсер + персистентность

## Что сделано

Первый под-проект модуля `estimates`. Пользователь загружает `.xlsx`-смету → она иерархически
парсится → **сохраняется** в БД: строки-узлы (разделы/подразделы) лежат со статусом `pending`,
`embedding = NULL`, ждут матчинга (SP2). Оригинальный файл кладётся в объектное хранилище
(S3/MinIO), наружу его ключ не отдаётся. Добавлены роуты загрузки/списка/просмотра/удаления с
проверкой владения. Матчинг и `score` — вне объёма SP1 (это SP2).

Спек: [docs/superpowers/specs/2026-06-22-estimate-hierarchical-parser-design.md](../superpowers/specs/2026-06-22-estimate-hierarchical-parser-design.md).
План: [docs/superpowers/plans/2026-06-22-estimate-hierarchical-parser.md](../superpowers/plans/2026-06-22-estimate-hierarchical-parser.md).
PR: [#6](https://github.com/zhukovvlad/ciw-tenders/pull/6) (база `main`). Коммиты `b6d0329..ea6468b`.

## Бэкенд (Clean Architecture)

- **Конфиг + зависимость:** `S3_*`-настройки + лимит загрузки в `Settings`; добавлен `boto3` (через `uv add`).
- **Миграция `0003` + ORM:** таблицы `estimates` (владелец, `filename`, `original_object_key`, `status`)
  и `estimate_rows` (узел дерева: `code`, `name`, `parent_code`, `section_type`, `depth`,
  `embedding_input`, `source_index`, `status`, `embedding` VECTOR NULL). Применяется на прод вручную (`just migrate`).
- **Иерархический парсер** ([estimate_parser](../../backend/app/services/)): чистый компонент без БД/AI.
  Из листа Excel строит дерево по точечному коду `№ раздела` (`1 → 1.1 → 1.1.5.1`), собирает
  обогащённый `embedding_input` (предки + имя), хранит `source_index` для стабильного порядка.
  Golden-тест на реальном файле (`temp/Смета — копия.xlsx`, skipif): 809 узлов / 1953 позиции.
- **Порты + сервис:** `EstimateRepository` / `ObjectStorage` (+ `StorageError`); `EstimateService.ingest`
  с жёстким порядком `parse → storage.put → repository.create` (сбой put → проброс, БД не тронута).
  Список/просмотр/удаление — симметричная проверка владения (`is_admin` обходит).
- **Адаптеры:** `SqlAlchemyEstimateRepository` (INSERT дерева одной транзакцией, маппинг без утечки
  `original_object_key`), `S3ObjectStorage` (ленивый `_ensure_bucket`, `__init__` без I/O, 503 на cold-start).
- **API:** `POST /api/estimates` (upload) с пред-валидацией в порядке `extension → size → signature → parse → storage`
  (storage недостижим, если упала любая пред-проверка); `GET` список/деталь, `DELETE`. Старый
  синхронный `POST /api/estimates/match` на этом этапе ещё жив (снят в SP2).

## Верификация (выполнена)

- Бэк: `uv run pytest` → **107 passed**; `uv run ruff check .` чисто.
- Golden-парсер прогнан локально (809 узлов / 1953 поз / 18 top / 15 СМР); реальная смета в git не коммитится.
- Миграция `0003` накатывается на прод-БД человеком (`just migrate`) — в тестах БД не поднимается.

## Решения и нюансы

- **Stateless-поток сохраняется только как структура для матчинга:** строки-узлы в БД + оригинал в
  S3/MinIO; никаких промежуточных результатов матчинга (это SP2).
- **`embedding_input` — best-effort на битых иерархиях** (расходится со строгим `template_parser`,
  который кидает; SP2 потребляет как есть) — зафиксировано в спеке финальным ревью.
- **`matched_article_id`/снимок ещё не существуют** — SP1 кладёт `status=pending`, `embedding=NULL`.
- Плановый Minor: устаревшие Starlette-константы `HTTP_413/422` → заменены на `*_CONTENT_TOO_LARGE`/
  `*_UNPROCESSABLE_CONTENT` (коммит `ea6468b`).
- Процесс: брейншторм → спек → план → subagent-driven реализация (8 задач, ревью spec+quality после
  каждой, финальное whole-branch ревью) → PR #6.

## Долг / на будущее

- MinIO orphan-reaper (осиротевшие объекты при сбое после put) — заметка в [TECH_DEBT](../TECH_DEBT.md).
