# Дизайн: структурное ядро сопоставления (tree matching) вместо построчного RAG

**Дата:** 2026-08-27 (спайк), 2026-08-28 (спека)
**Статус:** дизайн согласован в диалоге; три круга внешнего ревью (Codex) — все блокеры закрыты, правки внесены в текст.
**Заменяет (после гейта §9):** ядро фаз 2–3 [PIPELINE.md](../../PIPELINE.md) — классификацию оргзаголовков, эмбеддинг узлов, порог 0.90, LLM-арбитр по top-K.
**Не трогает:** парсер и позиционный резолв предков, таблицы `estimates`/`estimate_rows`, ревью-решения (`review_status`/`final_*`), экспорт, Celery-обёртку, авторизацию, эмбеддинги **справочника** (нужны поиску на карточке).

---

## 1. Диагноз и данные

Пайплайн сопоставляет каждую строку сметы независимо: крошка → эмбеддинг → top-5 по косинусу → порог → арбитр, который видит голые имена кандидатов без кодов, предков и соседей ([llm_matching_common.py:29](../../../backend/app/infrastructure/ai/llm_matching_common.py#L29)). Самый сильный сигнал — структура — выбрасывается до решения. Все кейсы A/B/C из [TECH_DEBT.md](../../TECH_DEBT.md) — симптомы этого.

Замеры по золотой смете (бенчмарк id=1, 809 узлов, 783 gold-метки) и `Шаблон.xlsx` (362 статьи, ~6k токенов):

| Факт | Значение |
|---|---|
| Имя строки дословно равно имени статьи | 337 / 783 (43%) |
| Метка внутри поддерева метки ближайшего размеченного предка | 687 / 758 (91%) |
| Имён, встречающихся с разными статьями (разводятся только родителем) | 69 |
| Раздел 6 сметы | буквальная копия раздела 6 справочника под «1 Этап ЖК» / «2 Этап БЦ» |
| Текущий RAG (`eval-run.log` 2026-06-27, devlog 2026-06-30) | top-1 74.1→77.0%; 372 confident / 388 needs_review; ~15 мин на смету |

Смета — производная справочника с вставленными орг-уровнями и дополнительным дроблением. Задача — разметка дерева, не поиск.

### Спайк (2026-08-27, одноразовый скрипт, в репо не входит)

LLM по разделу целиком, полный справочник в промпте, 20 вызовов, без эмбеддингов и оргфильтра:

| Модель | top-1 | Каркас (26 org-строк) | Время LLM | Токены in/out | Цена |
|---|---|---|---|---|---|
| RAG (прод) | 77.0% | 26/26, FP 0 | ~15 мин | — | — |
| Sonnet 4.6 | 94.9% (743/783) | 26/26, FP 0 | 149 с | 226k / 14k | $0.89 |
| Sonnet 5 | 95.1% (745/783) | 25/26, FP 1 | 423 с (reasoning) | 228k / 43k | $0.88 |
| Haiku 4.5 | 88.3% | 26/26, FP 4 | 72 с | 226k / 14k | $0.30 |

Детерминированный exact-match слой перед LLM оказался лишним и вредным (голое «Прочее» → корневое `99`); в дизайн не входит. Остаток ошибок — в основном регламентные сёстры (`8.1.4/8.1.5`, `9.1/9.2`, «ЗИП» → `99` vs `13.99`) — закрываются фондом решений.

---

## 2. Решения (что и почему)

| Решение | Обоснование |
|---|---|
| Новый движок за флагом `matching_engine = "tree" \| "rag"`, default `rag` до гейта §9; RAG-путь вырезается отдельным PR | Откат конфигом; харнесс гоняет оба движка на одном бенчмарке |
| Единица работы — **чанк раздела** (корень + потомки, ≤ N строк и ≤ бюджета токенов), не строка | Модель видит родителя, соседей, повтор имён; 18–40 вызовов на смету вместо ~1200 обращений |
| Полный справочник в каждом вызове, префикс кэшируется (prompt caching) | 362 статьи = 6k токенов; retrieval не нужен |
| Уверенность — самооценка модели `sure` + структурная валидация, без косинуса | Один проход; калибровка меряется харнессом (§9, группа C) |
| Кандидаты на карточке — структурные соседи + альтернатива модели; `score` становится nullable | 27 из 40 оставшихся ошибок спайка — сёстры выбранной статьи |
| Фонд решений: ключ v3 `(имя, доверенная статья предка)`, вычисляется **в обходе**; прецеденты фонда — в промпт | Регламент («ЗИП → 99») обобщается на похожие строки; ключ v2 (вся крошка) ломался от правки любого предка |
| Fail-closed: ошибка формата никогда не даёт `confident` или `no_match` | Асимметрия ошибок пайплайна сохраняется |

---

## 3. Домен

### 3.1. Сущности и DTO (`domain/entities.py`)

```python
@dataclass(frozen=True, slots=True)
class TreeNode:
    """Строка сметы для движка: контекст + цель. Читается fetch_tree в порядке source_index."""
    id: int
    source_index: int
    depth: int                 # число сегментов кода (как в парсере)
    code: str
    name: str
    status: str                # EstimateRowStatus
    review_status: str         # ReviewStatus
    matched_code: str | None   # AI-снимок
    matched_article_id: int | None
    final_code: str | None     # решение оператора
    final_article_id: int | None   # нужен промоушену (§6.2) — фонд якорится на id статьи

@dataclass(frozen=True, slots=True)
class CatalogArticle:
    id: int
    code: str
    name: str
    parent_code: str | None

@dataclass(frozen=True, slots=True)
class FundPrecedent:
    name: str
    parent_article_code: str   # "" для корня
    article_code: str
    article_name: str
    votes: int

@dataclass(frozen=True, slots=True)
class SectionMatchRequest:
    nodes: list[TreeNode]                  # чанк в порядке документа
    ancestors: list[tuple[TreeNode, str | None]]   # путь предков чанка с эффективными кодами (для не-корневых чанков)
    hints: dict[int, tuple[str, bool]]     # node_id → (код, trusted): [уже: код] / [предположительно: код]
    targets: frozenset[int]                # node_id, по которым нужен вердикт
    catalog: list[CatalogArticle]
    precedents: list[FundPrecedent]

@dataclass(frozen=True, slots=True)
class NodeVerdict:
    node_id: int
    kind: Literal["article", "org", "none"]
    article_code: str | None
    sure: bool
    alt_code: str | None

@dataclass(frozen=True, slots=True)
class AncestorContext:
    trusted_code: str | None       # код ближайшего ДОВЕРЕННОГО предка; None у корня
    has_uncertain_barrier: bool    # между узлом и trusted_code есть предок с недоверенным вердиктом
```

`MatchCandidate.score: float | None` (было `float`) — **осознанное изменение контракта**, см. §7.

### 3.2. Порт (`domain/ports.py`)

```python
class TreeMatcher(ABC):
    @abstractmethod
    def match_section(self, req: SectionMatchRequest) -> list[NodeVerdict]: ...
```

Единственный новый внешний порт. `TransientError` — тот же, что у существующих адаптеров.

Расширения `EstimateRepository`:
- `fetch_tree(estimate_id) -> list[TreeNode]` — все строки, `ORDER BY source_index`.
- `save_node_match_cas(node_id, result, expected_statuses) -> bool` — `UPDATE … WHERE id=… AND status IN (:expected) AND review_status='unreviewed'`; `False` = проиграли гонку (ревью или конкурент).
- `refresh_tree_node(node_id) -> TreeNode` — перечитать одну строку после проигранного CAS.
- `count_dependents(estimate_id, source_index_from, source_index_to) -> int` — число строк в позиционном диапазоне с `status ∈ {confident, matched_fund}` и `review_status='unreviewed'` (§7.3).

`ArticleRepository.list_catalog() -> list[CatalogArticle]` — весь справочник (id, code, name, parent_code).

`DecisionFundRepository.records_for_names(names: Sequence[str], version) -> list[FundPrecedent]` — **один** запрос на чанк: все живые записи фонда версии 3 по нормализованным именам целей (любой родитель). Из этого набора локально, без БД, решаются и exact-hit (полный ключ → ровно одна статья), и прецеденты для промпта (§6.3). `FundPrecedent` дополняется `article_id` и `key` (полный ключ v3).

### 3.3. Чистые функции (`domain/tree_matching.py`, без I/O)

**`resolve_parents(nodes) -> list[int | None]`** — индексы родителей через существующую `resolve_ancestor_indices(depths)` из [classification.py](../../../backend/app/domain/classification.py) (позиционный стек по `depth`; скачок глубины → ближайший открытый предок; `parent_code` **не** используется — коды повторяются между этапами).

**`effective_ancestor_context(idx, nodes, parents) -> AncestorContext`** — единственная функция и для движка, и для фонда, и для промоушена. Подъём по предкам:

| Предок | Действие |
|---|---|
| `review_status ∈ {confirmed, overridden}` | **доверенный**: `trusted_code = final_code`, стоп |
| `status ∈ {confident, matched_fund}` и `unreviewed` | **доверенный**: `trusted_code = matched_code`, стоп |
| `status = needs_review` | недоверенный: `has_uncertain_barrier = True`, подниматься дальше |
| `rejected`, `excluded`, `no_match`, `error`, `pending` | прозрачный: подниматься дальше |
| предков не осталось | `trusted_code = None`, барьер как накоплен — **корень доверенная база** |

Пример: `confident A → needs_review B → C` ⇒ `AncestorContext("A", True)`.

**`split_sections(nodes, parents, *, max_rows, budget) -> list[Chunk]`** — рекурсивное `split(subtree_root)`:
1. если поддерево укладывается в `max_rows` **и** токен-бюджет — один чанк;
2. иначе чанк-«шапка» = корень + дети целыми поддеревьями, пока влезают (жадно, по документу); каждый не влезший ребёнок обрабатывается `split(child)` рекурсивно — его чанки получают путь предков (§3.1 `ancestors`);
3. ребёнок, чьё поддерево само больше лимита, **не** кладётся в шапку целиком — он идёт в п. 2 как отдельный корень (для цепочки без сиблингов это даёт чанки из одного узла-звена, что допустимо: лимит гарантирован, рекурсия завершается, так как каждый шаг уменьшает глубину);
4. один узел, не влезающий в токен-бюджет сам по себе (имя длиннее бюджета), → цели `error` с `tree_row_too_large`.

Чанки одного раздела упорядочены по документу: **родительский чанк всегда раньше дочернего**. То же `split` используется при делении после `finish_reason=length` (§5.1), с уменьшенным лимитом строк.

**`estimate_tokens(text) -> int`** = `ceil(len(text) / 3)` — консервативно для кириллицы (на спайке оценка 6.0k против факта 5.6k у справочника).

**`build_hints(chunk, contexts)`** — для не-целей: доверенные → `[уже: код]`, `needs_review` → `[предположительно: код]`; для целей подсказок нет.

**`validate_verdicts(verdicts, req, catalog, contexts) -> dict[int, Validated]`**, где `Validated = (verdict | None, flags)`. Проверки по порядку:
1. `node_id ∉ targets` → игнор (лог debug);
2. дубликат `node_id` → берётся первый, остальные лог warning;
3. типы полей (`kind` из множества, `sure` bool, коды str|None) — иначе флаг `malformed`;
4. согласованность: `article` без кода или `org`/`none` с кодом → `inconsistent`;
5. `article_code ∉ catalog` → `unknown_code`; `alt_code ∉ catalog` или `== article_code` → `alt_code = None` (без флага);
6. `outside_parent`: код не в поддереве `trusted_code` и `trusted_code` не в поддереве кода (роллап вверх допустим) — **только при доверенном контексте** (`trusted_code is not None`);
7. цель без вердикта → `missing`.

**`to_node_match(validated, ctx, catalog) -> NodeMatch`**:

| Вход | Статус | Примечание |
|---|---|---|
| `org`, без флагов | `excluded` | как оргфильтр сейчас; обратимо |
| `article`, `sure`, без флагов, `not ctx.has_uncertain_barrier` | `confident` | единственный путь в `confident` |
| `article`, `sure`, `ctx.has_uncertain_barrier` | `needs_review` | уверенность на сомнительной опоре не наследуется |
| `article`, `not sure` или `outside_parent` | `needs_review` | |
| `none`, без флагов | `no_match` | легитимный отказ |
| `unknown_code`, `inconsistent`, `malformed` | `needs_review`, `matched_* = NULL` | кандидаты — дети `trusted_code` (+ сама статья); fail-closed |
| `missing` | `error`, `match_error="tree_missing_verdict"` | ре-триггер доберёт |

`candidates` снимка (`neighbors(catalog, code, alt_code, limit=5)`): выбранная статья, `alt_code`, сёстры выбранной, её родитель — `score=None`. Для `unknown_code`/`inconsistent` — дети `trusted_code` и сама `trusted_code`.

**`fund_key_v3(node, ctx) -> str | None`** — `normalize(name) + "" + (ctx.trusted_code or "")`; `None`, если `ctx.has_uncertain_barrier` (exact-hit при барьере не применяется, §6.1). Хэш — `cache_key_hash` как сейчас. Константа `FUND_KEY_VERSION = 3` в `domain/decision_fund.py`, **отдельно** от `CRUMB_DERIVATION_VERSION` (та уходит вместе с RAG).

---

## 4. Сервис (`services/estimate_matching_service.py`)

При `engine == "tree"` метод `match_estimate` сохраняет каркас (advisory-lock, `running`, финализация `ready`/`partial_error`, summary-лог, `finally: release`), но тело стадий другое:

```
lock → running
catalog = articles.list_catalog();  пусто → status=blocked, code="catalog_empty"
catalog_tokens > 25% окна → status=blocked, code="catalog_too_large"
tree = estimates.fetch_tree(id);  parents = resolve_parents(tree)     # tree — РАБОЧЕЕ дерево, mutable
EXPECTED = (pending, error, no_match)
is_target(i) = tree[i].status ∈ EXPECTED ∧ tree[i].review_status == unreviewed
failed_roots = set()                                                  # индексы корней упавших поддеревьев

def commit(i, result):                                                # единая точка записи
    ok = estimates.save_node_match_cas(tree[i].id, result, EXPECTED)
    tree[i] = tree[i].with_result(result) if ok else estimates.refresh_tree_node(tree[i].id)

def contexts(idxs): return {i: effective_ancestor_context(i, tree, parents) for i in idxs}

def resolve_exact(i, ctx_i, records):                                 # локально, без БД
    key = fund_key_v3(tree[i], ctx_i)                                 # None при барьере
    live = {r.article_id for r in records if r.key == key}
    return single(live) if key is not None else None

for chunk in split_sections(...):                                     # порядок документа
    if any(r ∈ ancestors_of(chunk.root) ∪ {chunk.root} for r in failed_roots):
        for i in chunk.targets(is_target): commit(i, error("tree_ancestor_failed"))
        continue                                                      # ← outer continue: чанк пропущен
    targets = [i for i in chunk if is_target(i)]
    records = fund.records_for_names(names_of(targets), FUND_KEY_VERSION) if fund_enabled else []   # 1 запрос на чанк

    # 4.1 pre-call exact-фонд — контекст, известный ДО вызова модели
    for i in targets (в порядке source_index):
        hit = resolve_exact(i, contexts([i])[i], records)             # контекст свежий: предыдущие commit уже в tree
        if hit: commit(i, matched_fund(hit))
    remaining = [i for i in targets if is_target(i)]
    if not remaining: continue

    # 4.2 LLM — контекст и подсказки ПЕРЕСЧИТАНЫ после pre-call записей
    ctx = contexts(chunk)
    req = SectionMatchRequest(nodes=chunk, ancestors=path_with_codes(chunk.root, tree, parents),
                              hints=build_hints(chunk, ctx), targets=remaining, catalog=catalog,
                              precedents=select_precedents(records, budget))
    try:
        verdicts = matcher.match_section(req)
    except TransientError as exc:
        failed_roots.add(chunk.root)
        for i in remaining: commit(i, error(f"tree_transient: {exc}"))
        continue                                                      # ← outer continue

    # 4.3 post-call — СВЕРХУ ВНИЗ; контекст ребёнка считается по уже принятому вердикту родителя
    for i in remaining (в порядке source_index):
        ctx_i = contexts([i])[i]
        hit = resolve_exact(i, ctx_i, records)                        # фонд авторитетнее модели; без БД
        if hit: commit(i, matched_fund(hit)); continue                # ← inner continue
        v = validate_one(verdicts.get(i), req, catalog, ctx_i)        # outside_parent по свежему trusted_code
        commit(i, to_node_match(v, ctx_i, catalog))                   # confident только без барьера

finalize: errors/unfinished → partial_error иначе ready
```

`fund_enabled` = `apply_fund ∧ FUND_KEY_VERSION-ветка реализована` (§11: в PR 1 обе фондовые ветки выключены константой, `records` пуст, `resolve_exact` всегда `None`, прецедентов нет).

Инварианты:
- **Контекст ≠ цели.** Все строки чанка идут в промпт; вердикт запрашивается и записывается только по целям. Повторный запуск не перепишет `confident`/`needs_review`/`matched_fund`/`excluded` — CAS по `status IN (pending, error, no_match)`.
- **Рабочее дерево всегда актуально.** Успешный CAS заменяет `TreeNode` результатом записи; проигранный — перечитыванием строки. Следующие узлы (в чанке и в дочерних чанках) видят свежие `status`/`matched_code`/`final_code`.
- **Один ответ обрабатывается сверху вниз.** Вердикт родителя принимается раньше ребёнка, и контекст ребёнка (`trusted_code`, барьер, ключ фонда, `outside_parent`) считается по уже принятому вердикту родителя, а не по состоянию до вызова. Признанное ограничение: **прецеденты** для строк, чей родитель решается тем же вызовом, запрашиваются по имени без родителя (§6.3) — модель видит их вместе с родительским контекстом каждого прецедента и сама сопоставляет.
- **Фонд авторитетнее модели, БД — один запрос на чанк.** `records_for_names` грузит все живые записи по именам целей до вызова; exact-hit и прецеденты решаются из этого набора локально. Exact-hit применяется дважды: до вызова (контекст доверенный до вызова — экономит токены ответа) и после (контекст стал доверенным внутри чанка) — в обоих случаях только без барьера. После pre-call записей контекст, путь предков и подсказки **пересчитываются** — модель видит `[уже: код]` родителя, закрытого фондом секунду назад.
- **Упавшее поддерево завершается консервативно.** `failed_roots` хранит корни упавших чанков; все последующие чанки, чей корень лежит в упавшем поддереве (включая его собственный корень при делении), получают `error` по целям. Чанки-сиблинги вне поддерева обрабатываются штатно.
- **Транзиент фиксируется.** Оставшиеся цели упавшего чанка и цели всех дочерних чанков раздела получают `error` с машинным `match_error` (`tree_transient` / `tree_ancestor_failed`) через тот же CAS — ретрай `no_match`-цели не может тихо остаться терминальным, `partial_error` гарантирован (как в RAG-пути, [estimate_matching_service.py:238](../../../backend/app/services/estimate_matching_service.py#L238)).
- **Порядок.** Чанки последовательны (дочерние зависят от эффективного контекста предков). Параллелизм между независимыми разделами — TECH_DEBT.
- `_classify_nodes`, `_apply_fund` (стадия до LLM), `_embed_nodes`, гейт `matching_readiness` при `tree` **не вызываются**.
- Сбой одного чанка не валит смету: его цели и цели дочерних чанков получают `error` (машинный код) → `partial_error` → ре-триггер берёт их как цели в том же порядке.

`build_estimate_matching_service` ([deps.py:181](../../../backend/app/api/deps.py#L181)) выбирает ветку по `settings.matching_engine`; `apply_fund=False` (харнесс) отключает и exact-hit, и прецеденты.

---

## 5. Инфраструктура

### 5.1. `OpenRouterTreeMatcher(TreeMatcher)` (`infrastructure/ai/openrouter_tree_matcher.py`)

`httpx` + `instrumented_call` + `retry_transient` — как у существующих адаптеров. Транзиенты: сеть, 429, 5xx, пустой `choices`. Промпт — из спайка, с полями `sure` и `alt`:

- **system:** роль, правила (структура; org только для чистого каркаса; корпуса внутри работы → статья родителя; роллап при дроблении; `none` для реальной работы без статьи; «Прочее» раздела — `X.99`, не корневое; строки `[уже: …]` не менять; формат ответа).
- **user:** `СПРАВОЧНИК` (иерархический список `(код) имя` с отступами) → `ПРЕЦЕДЕНТЫ` (§6.3, опционально) → `КОНТЕКСТ` (путь предков чанка с эффективными кодами; только для не-корневых чанков) → `ФРАГМЕНТ` (`id | код | имя` с отступами и подсказками).
- Ответ: JSON-массив `{"i": id, "code": "<код|org|none>", "sure": bool, "alt": "<код>|null}`; парсинг — первый `[...]`-блок, `json.loads`; невалидный JSON → все цели `missing`.
- `cache_control: {"type": "ephemeral"}` на блоке system+справочник (Anthropic prompt caching через OpenRouter) — справочник одинаков во всех вызовах сметы.
- Параметры: `temperature=0`, `reasoning={"effort": settings.tree_reasoning_effort}` (default `low`), `max_tokens = rows × tree_output_reserve_per_row + 512`.
- `finish_reason == "length"` → чанк делится тем же `split` с `max_rows // 2` (минимум `tree_min_chunk_rows=10`) и повторяется; ниже минимума → цели чанка `error` (`tree_output_truncated`). Невалидный JSON при `finish_reason == "stop"` — **не** причина деления: это `missing` по всем целям (строка выше).

### 5.2. Бюджет контекста

Все оценки — `estimate_tokens`. Инварианты проверяются **в начале каждого прогона** (каталог меняется в рантайме), не при старте приложения:

| Ограничение | Значение / действие |
|---|---|
| `catalog_tokens ≤ 0.25 × tree_context_window` | иначе `blocked`, `catalog_too_large` |
| `system + catalog + precedents + chunk + reserve ≤ 0.80 × window` | чанк режется по строкам **и** по токенам |
| `precedents_tokens ≤ tree_precedents_budget` | лишние прецеденты отбрасываются (по `votes`) |

Startup-валидация только конфигурации: слаг непустой, `tree_context_window > 0`, `0 < tree_chunk_rows`, без сетевых вызовов.

### 5.3. Конфиг (`core/config.py`)

| Ключ | Default | Смысл |
|---|---|---|
| `matching_engine` | `rag` (→ `tree` после гейта) | выбор ядра |
| `openrouter_tree_model` | `anthropic/claude-sonnet-5` | слаг модели |
| `tree_reasoning_effort` | `low` | рассуждение модели (на спайке без ограничения — ×3 output-токенов) |
| `tree_context_window` | `200000` | окно модели, задаётся явно |
| `tree_chunk_rows` | `120` | верх строк в чанке |
| `tree_min_chunk_rows` | `10` | низ при делении после обрезки |
| `tree_output_reserve_per_row` | `48` | резерв ответа на строку |
| `tree_precedents_budget` | `2000` | токены на прецеденты |

Ожидаемая стоимость (Sonnet 5, effort low, кэш префикса): ~$0.25–0.40 на смету в 800 узлов, ~2.5 мин. Без кэша — $0.88 (замер спайка).

---

## 6. Фонд решений (v3)

### 6.1. Lookup — в обходе, не до LLM

Ключ `fund_key_v3(node, ctx)` вычисляется для каждой цели дважды (§4): до вызова модели — по контексту предков из предыдущих чанков/прогонов, и после — сверху вниз по принятым вердиктам этого же чанка. При `has_uncertain_barrier` ключ `None` — exact-применение **пропускается**, а находка (если есть) уходит в прецеденты как подсказка. Хит с ровно одной живой статьёй (`resolve_fund_decision` как сейчас) → `matched_fund` через тот же CAS, снимок без кандидатов; post-call хит имеет приоритет над вердиктом модели. К БД — один `records_for_names` на чанк; разрешение по полному ключу — локально. Смешение с v2 исключено фильтром `crumb_version = FUND_KEY_VERSION` в `lookup`; старые записи v2 инертны, их чистит существующий `rebuild`.

### 6.2. Promotion — то же дерево, та же функция

`DecisionFundService.promote` читает **`fetch_tree`** (не плоский `PromotableRow` — он удаляется вместе с `fetch_promotable_rows`), считает `resolve_parents`, и для каждой строки с `review_status ∈ {confirmed, overridden}` и непустым `final_article_id` строит `fund_key_v3(node, effective_ancestor_context(...))`. Ключ `None` (барьер) → строка не промоутится. Анти-накрутка (`matched_fund` + `confirmed` не рекрутируется) сохраняется. Тест-инвариант: ключ промоушена строки эталона равен ключу lookup той же строки в свежей копии сметы, где предки в тех же статусах.

### 6.3. Прецеденты в промпт

`select_precedents(records, budget)` строит блок из того же набора `records_for_names(names)` — записей фонда версии 3 по **нормализованным именам** целей чанка (все ключи с этим именем, любой родитель), JOIN к живым статьям. Запрос по имени, а не по полному ключу, — сознательно: для строк, чей родитель решается тем же вызовом, parent-код до вызова неизвестен (§4); каждый прецедент несёт свой `parent_article_code`, и модель сопоставляет его с контекстом строки сама. Правила: полный ключ `(имя, родитель)` с **несколькими** статьями — конфликт, в промпт не идёт (счётчик в summary); дедуп по полному ключу; сортировка `votes desc`; отсечение по `tree_precedents_budget`. Формат блока: `имя | в разделе (код родителя) имя родителя → (код) статья — N решений`.

### 6.4. Инвалидация

Как в спеке фонда 2026-06-30 (гибрид C): переименование статьи — ключ жив; удаление — отсекается JOIN-ом; смена `FUND_KEY_VERSION` — старые ключи инертны. Правка имени **предка** в смете больше не рвёт ключи потомков (в ключе только код статьи предка).

---

## 7. API и фронтенд — явные отклонения от «не меняется»

### 7.1. `MatchCandidateOut.score: float | None`

Домен `MatchCandidate.score: float | None`, DTO, `frontend/src/lib/types.ts`. `ReviewCard` не рендерит бейдж score при `null` (одно условие + снимок-тест). Сортировка кандидатов на карточке — по порядку снимка (у RAG он уже отсортирован по score).

### 7.2. Ответ `PATCH /estimates/{id}/rows/{row_id}/review`

Добавляется поле `dependents_hint: int` — число строк в **позиционном поддереве** строки (`source_index` от следующей строки до первой с `depth ≤` текущей) со `status ∈ {confident, matched_fund}` и `review_status='unreviewed'`. Считает review-сервис через `count_dependents`; `save_review_decision` остаётся записью одной строки. Возвращается только при `action ∈ {pick, reject}` (override/reject), иначе `0`. Provenance в снимке нет, поэтому формулировка честная: «N дочерних строк **могут** зависеть от прежнего выбора» (точный учёт через `context_source_node_id` — TECH_DEBT).

### 7.3. Фронт

При `dependents_hint > 0` после коммита — toast с текстом подсказки и действием «Показать в таблице» → грид с фокусом на первой строке поддерева (`focusRowNumber`, механизм уже есть в `ReviewScreen`). Ключи i18n `review.dependentsHint`/`review.showDependents` в `ru`/`tr`. Тесты: рендер toast по ответу, переход в грид, отсутствие toast при `confirm`.

Автоматический пересмотр потомков после override/reject **не делается**: снимок иммутабелен (как сейчас), решение оператора авторитетно.

---

## 8. Харнесс и метрики (`domain/benchmark.py`, `scripts/eval_matching.py`)

- `just eval-matching --engine tree|rag [--benchmark …]`; RAG-baseline снимается один раз до PR 1 и замораживается сводкой в `docs/benchmarks/2026-08-rag-baseline.json` (без построчника).
- **`top1_strict`** — знаменатель = все gold-`matchable`, `error` — промах (существующий `top1` с исключением `error` остаётся для сопоставимости с историей).
- **Группа C — калибровка:**
  - `precision_confident` = верных `confident` / **всех** `confident` (включая уверенные article-вердикты на gold `structural`/`no_article` — они ложные);
  - `confident_coverage` = `confident` верных / gold-`matchable`;
  - `confident_on_structural` — отдельной строкой;
  - `review_rate` = (`needs_review` + `no_match` + `error`) / gold-`matchable`;
  - `error_rate` = узлов gold-`matchable` со `status=error` / всех gold-`matchable`;
  - число вызовов, prompt/completion токены, секунды.
- Гейт двойной: id=1 (шаблонная) и id=2 (**целая** нешаблонная смета, размечается специалистом и сидится тем же `benchmark-seed`).

---

## 9. Definition of Done и гейты

**PR 1–3 (движок за флагом, default `rag`):** полный сьют зелёный; `ruff`/`tsc -b`/`eslint`/`vitest`; `just eval-matching --engine tree` проходит на id=1 без падений; спайковые цифры воспроизведены харнессом (top1_strict ≥ 93%).

**Гейт смены default на `tree` и старта PR 4 (вырезание RAG)** — одновременно:

| Бенчмарк | Условие |
|---|---|
| id=1 (шаблонная) | `top1_strict ≥ 93%`, `precision_confident ≥ 97%`, `confident_coverage ≥ 60%` (предварительно; калибруется в PR 2 по факту доли `sure`), `error_rate ≤ 1%` |
| id=2 (нешаблонная, целая) | `top1_strict(tree) ≥ top1_strict(rag) − 2 п.п.`, `precision_confident ≥ 95%`, `error_rate ≤ 1%` |
| оба | `confident_on_structural` не выше, чем у RAG-baseline; `review_rate` — отчётной строкой |

Пока id=2 не размечен — default остаётся `rag`, вырезание не начинается.

---

## 10. Тесты

- **Домен:** `resolve_parents` (дубли кодов между этапами, скачок глубины); `effective_ancestor_context` (вся таблица §3.3, пример A→B→C, корень); `split_sections` (раздел-одиночка, деление по детям, порядок «родитель раньше ребёнка», лимит по токенам, **единственный ребёнок больше лимита → рекурсия, цепочка без сиблингов завершается**, узел больше бюджета → `tree_row_too_large`); `validate_verdicts` (каждый флаг, дубликат, чужой `node_id`, `alt == code`); `to_node_match` (полная матрица kind × sure × барьер × флаги — единственный путь в `confident`); `neighbors`; `fund_key_v3` (барьер → `None`); `estimate_tokens`.
- **Сервис** (фейк `TreeMatcher` в `tests/fakes.py`): happy path; контекст ≠ цели (не-цели не перезаписываются); **pre-call фонд закрыл родителя → LLM-запрос ребёнка содержит свежий `[уже: код]`** (проверяется через захваченный `SectionMatchRequest` фейка); ровно один вызов фонда на чанк (счётчик фейка); упавший сиблинг-раздел не влияет на соседний; **вердикт родителя из того же ответа входит в контекст ребёнка** (одинаковые имена «Прочее» под разными разделами → разные `X.99`, `outside_parent` срабатывает по свежему родителю); **успешный вердикт предкового чанка входит в контекст дочернего** (`trusted_code` виден без перечитывания); транзиент чанка → оставшиеся цели и цели дочерних чанков в `error` с машинным кодом → `partial_error` даже если единственной целью был `no_match`; ре-триггер доматчивает только `error`; CAS `False` на предке → перечитан `final_code` до потомков; exact-hit фонда пропущен при барьере, а post-call хит побеждает вердикт модели.
- **Адаптер** (стаб httpx): валидный JSON; битый JSON → все цели `missing`; `finish_reason=length` → деление чанка; ниже минимума → `error`; `cache_control` присутствует в теле запроса.
- **Репозиторий/фонд:** `save_node_match_cas` по обоим предикатам (интеграционный, `TEST_DATABASE_URL`); `records_for_names` + `select_precedents` — конфликт по полному ключу исключён, `votes` сортировка, один запрос на чанк; инвариант «ключ промоушена = ключ lookup».
- **Харнесс:** `top1_strict`, группа C на синтетических исходах (в т.ч. уверенный матч на `structural` снижает precision).
- **API/фронт:** `score: null` сериализуется и не рендерится; `dependents_hint` считается по позиционному поддереву и равен `0` при `confirm`; toast и переход в грид.

---

## 11. План PR

1. **Ядро за флагом — без фонда.** Домен (§3.3, включая `fund_key_v3`/`effective_ancestor_context` — они нужны валидации и барьеру) + порт + фейк + `fetch_tree`/`refresh_tree_node`/`save_node_match_cas`/`list_catalog` + сервис (§4) + адаптер (§5) + конфиг + `score` nullable сквозь стек (§7.1). **Промежуточная семантика:** `fund_enabled = False` жёстко — `records` пуст, exact-hit не срабатывает, блок прецедентов не рендерится; `matched_fund` для `tree` в PR 1 недостижим. Default `rag`. Включённый вручную `tree` полностью работоспособен без фонда.
2. **Харнесс.** `--engine`, `top1_strict`, группа C, замороженный RAG-baseline, сид бенчмарка id=2 (нужен специалист-разметчик — запрос отдельно). Замер PR 1 — ориентировочный, **не гейт**.
3. **Фонд v3.** `FUND_KEY_VERSION`, `records_for_names`, pre/post exact в обходе, promotion по дереву, прецеденты в промпт, снятие константы `fund_enabled`; `dependents_hint` + фронт-подсказка (§7.2–7.3). **Гейт §9 выполняется только после PR 3.**
4. **Гейт → default `tree` → вырезание RAG:** `_classify_nodes`/`WorkTypeClassifier`/`openrouter_classifier`, `_embed_nodes` узлов, `MatchingService.match_one`/`LLMMatcher`/арбитр-адаптеры, порог/`top_k`, гейт `matching_readiness` в матчинге, `CRUMB_DERIVATION_VERSION`, `PromotableRow`; миграция — `DROP COLUMN estimate_rows.embedding`; PIPELINE.md переписывается.

---

## 12. Вне области / TECH_DEBT

- Параллельная обработка независимых разделов (сейчас строго последовательно).
- Точный provenance контекста в снимке (`context_source_node_id`) и автоматический пересмотр потомков после override/reject.
- Удаление эмбеддингов справочника (их использует поиск по каталогу на карточке).
- Пересмотр разметки gold там, где спайк показал регламентную неоднозначность (`8.1.4/8.1.5`, `9.1/9.2`, «ЗИП»), и `article_renamed=73` — освежить снимки имён.
- Автоматическая калибровка порога `confident_coverage` по накопленным ревью.
