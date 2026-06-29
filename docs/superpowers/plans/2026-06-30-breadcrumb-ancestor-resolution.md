# Позиционный резолв предков крошки (фикс Кейса D) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Чинить тихую контаминацию крошки (`embedding_input`) на многоэтапных сметах — резолвить имена предков по ближайшему предшествующему вхождению кода, а не по глобальному словарю первого вхождения.

**Architecture:** Чистая доменная функция `resolve_ancestor_indices(codes)` (без ORM/имён) возвращает для каждого узла индексы предков + флаг отката. Три потребителя (`_classify_nodes`, его LLM-контекст, `estimate_parser`) мапят индексы в имена/классы и строят крошку каждый по-своему. Поведенческий фикс — только смена резолва предков; `is_leaf`, порог, арбитр не трогаются.

**Tech Stack:** Python 3.11+, FastAPI/Clean Architecture, pytest, `uv`, pandas (парсер), pgvector (вне скоупа фикса).

**Спек:** [docs/superpowers/specs/2026-06-30-breadcrumb-ancestor-resolution-design.md](../specs/2026-06-30-breadcrumb-ancestor-resolution-design.md)

## Global Constraints

- ruff line-length 100, `target py311`; каждый модуль начинается с `from __future__ import annotations`; type hints обязательны.
- Комментарии/строки — по-русски, как в окружающем коде.
- Юнит-тесты НЕ ходят в реальную БД/AI — только фейки портов ([tests/fakes.py](../../../backend/tests/fakes.py)) и прямые вызовы.
- Команды бэка — строго `uv run` из `backend/` (на Windows: `uv run --directory backend ...`). Не вызывать системный python/pip.
- Файлы в LF. Перед коммитом — `uv run ruff check .`.
- Ветка: `fix/breadcrumb-ancestor-collision` (уже создана, на ней лежит спек).

---

### Task 1: Доменная функция `resolve_ancestor_indices`

**Files:**
- Modify: `backend/app/domain/classification.py` (добавить функцию + импорты `bisect`, `Sequence`)
- Test: `backend/tests/test_classification.py` (добавить тесты в конец)

**Interfaces:**
- Produces: `resolve_ancestor_indices(codes: Sequence[str]) -> list[list[tuple[int, bool]]]` — для каждой позиции `i` список `(индекс_предка, is_fallback)` от корня к родителю.

- [ ] **Step 1: Написать падающие юнит-тесты**

Добавить в конец `backend/tests/test_classification.py`:

```python
from app.domain.classification import resolve_ancestor_indices


def test_resolve_no_collision_matches_truncation() -> None:
    res = resolve_ancestor_indices(["1", "1.1", "1.1.1"])
    assert res == [[], [(0, False)], [(0, False), (1, False)]]


def test_resolve_nearest_preceding_on_collision() -> None:
    # код 6.4 встречается дважды; 6.4.1 второго этапа → ближайший предшествующий 6.4
    codes = ["6", "6.4", "6.4.1", "6.5", "6.4", "6.4.1"]
    #          0     1      2       3     4      5
    res = resolve_ancestor_indices(codes)
    assert res[2] == [(0, False), (1, False)]  # первый 6.4.1 → 6.4@1
    assert res[5] == [(0, False), (4, False)]  # второй 6.4.1 → 6.4@4 (НЕ @1)


def test_resolve_nearest_beats_first_when_first_differs() -> None:
    # 6.5 ЖК="модульный", БЦ="навесной типового"; 6.5.1 БЦ обязан взять БЛИЖАЙШИЙ 6.5,
    # а не первое вхождение (иначе крошка получит «модульный» вместо «навесной типового»).
    codes = ["6.5", "6.5.1", "6.5", "6.5.1"]
    #          0      1        2      3
    res = resolve_ancestor_indices(codes)
    assert res[1] == [(0, False)]   # первый 6.5.1 → 6.5@0
    assert res[3] == [(2, False)]   # второй 6.5.1 → 6.5@2 (ближайший), НЕ @0


def test_resolve_preserves_context_when_header_not_restated() -> None:
    # перегородки: 5.1 (заголовок) один раз; 5.1.1 дважды (этап 2 не повторил 5.1).
    # Второй 5.1.1 берёт тот же 5.1 — контекст сохранён, не fallback.
    codes = ["5", "5.1", "5.1.1", "5.2", "5.1.1"]
    #          0    1      2        3      4
    res = resolve_ancestor_indices(codes)
    assert res[2] == [(0, False), (1, False)]
    assert res[4] == [(0, False), (1, False)]  # тот же контекст, что у первого 5.1.1


def test_resolve_fallback_when_parent_only_later() -> None:
    # child-before-parent: 1.1 стоит ВЫШЕ 1 → откат к первому вхождению (индекс > i), флаг True
    res = resolve_ancestor_indices(["1.1", "1"])
    assert res[0] == [(1, True)]
    assert res[1] == []


def test_resolve_skips_absent_ancestor() -> None:
    # кода-предка нет вовсе ("1", "1.2" отсутствуют) → пропуск
    assert resolve_ancestor_indices(["1.2.3"]) == [[]]


def test_resolve_segment_not_string_prefix() -> None:
    # предки 1.10 — это [1], не [1, 1.1]
    res = resolve_ancestor_indices(["1", "1.1", "1.10"])
    assert res[2] == [(0, False)]


def test_resolve_monotonic_invariant_on_realistic_input() -> None:
    # property: для is_fallback=False индексы строго возрастают и < i; fallback допускает >= i
    codes = ["6", "6.4", "6.4.1", "6.5", "6.4", "6.4.1", "1.1", "1"]
    res = resolve_ancestor_indices(codes)
    for i, chain in enumerate(res):
        preceding = [j for j, fb in chain if not fb]
        assert preceding == sorted(preceding)
        assert len(set(preceding)) == len(preceding)
        assert all(j < i for j in preceding)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run --directory backend pytest tests/test_classification.py -k resolve -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_ancestor_indices'`.

- [ ] **Step 3: Реализовать функцию**

В `backend/app/domain/classification.py` добавить импорты вверху (после `from __future__ import annotations`):

```python
import bisect
from collections.abc import Sequence
```

И функцию (в конец файла):

```python
def resolve_ancestor_indices(codes: Sequence[str]) -> list[list[tuple[int, bool]]]:
    """codes — коды узлов В ПОРЯДКЕ документа. Для каждой позиции i возвращает
    список (индекс_предка, is_fallback) от корня к родителю.

    Код-предок разрешается в БЛИЖАЙШЕЕ предшествующее вхождение (макс. индекс < i,
    is_fallback=False). Если предшествующего нет — первое вхождение (is_fallback=True;
    индекс может быть >= i: контекст тянется СНИЗУ, крошка для такого предка ненадёжна).
    Код-предок, не встречающийся вовсе, пропускается. Фикс Кейса D: на многоэтапных
    сметах коды дублируются с разным смыслом, глобальный словарь брал бы первое имя."""
    occ: dict[str, list[int]] = {}
    for i, code in enumerate(codes):
        occ.setdefault(code, []).append(i)
    result: list[list[tuple[int, bool]]] = []
    for i, code in enumerate(codes):
        segs = code.split(".")
        chain: list[tuple[int, bool]] = []
        for k in range(1, len(segs)):
            positions = occ.get(".".join(segs[:k]))
            if not positions:
                continue
            j = bisect.bisect_left(positions, i) - 1  # ближайшее вхождение < i
            chain.append((positions[j], False) if j >= 0 else (positions[0], True))
        result.append(chain)
    return result
```

- [ ] **Step 4: Запустить — убедиться, что зелено**

Run: `uv run --directory backend pytest tests/test_classification.py -k resolve -v`
Expected: PASS (8 тестов).

- [ ] **Step 5: Линт + коммит**

```bash
uv run --directory backend ruff check app/domain/classification.py tests/test_classification.py
git add backend/app/domain/classification.py backend/tests/test_classification.py
git commit -m "feat(matching): resolve_ancestor_indices — позиционный резолв предков (фикс Кейса D)"
```

---

### Task 2: Интеграция в `_classify_nodes` (авторитетный путь)

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py` (импорт + переписать `_classify_nodes`, удалить `_ancestor_names` и `_ancestor_codes`, оставить `_parent_of`)
- Test: `backend/tests/test_estimate_matching_service.py` (добавить тест коллизии)

**Interfaces:**
- Consumes: `resolve_ancestor_indices(codes) -> list[list[tuple[int, bool]]]` (Task 1).

- [ ] **Step 1: Написать падающий сервис-тест**

Добавить в `backend/tests/test_estimate_matching_service.py` (рядом с другими `_seed_tree`-тестами):

```python
def test_classify_collision_distinct_breadcrumbs() -> None:
    # фикс Кейса D: две строки 6.4.1 (разных этапов) ДОЛЖНЫ получить разные крошки.
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [
        ("6", "Устройство фасадов", None),
        ("6.4", "навесной фасад типового этажа", "6"),
        ("6.4.1", "Устройство подсистемы", "6.4"),
        ("6.5", "модульный фасад", "6"),
        ("6.2", "2 Этап БЦ", None),               # org-обёртка → срежется
        ("6.4", "навесной фасад 1 этажа", "6"),   # код 6.4 повторно, другой смысл
        ("6.4.1", "Устройство подсистемы", "6.4"),
    ])
    svc = _classify_svc(repo, classifier=FakeWorkTypeClassifier(default=WorkClass.WORK))
    svc._classify_nodes(est.id)  # noqa: SLF001
    crumbs = [r.embedding_input for r in repo.get(est.id, 1, is_admin=True).rows
              if r.code == "6.4.1"]
    assert len(crumbs) == 2
    assert crumbs[0] != crumbs[1]                  # сейчас байт-в-байт одинаковы
    assert any("типового" in c for c in crumbs)
    assert any("1 этажа" in c for c in crumbs)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run --directory backend pytest tests/test_estimate_matching_service.py::test_classify_collision_distinct_breadcrumbs -v`
Expected: FAIL — `crumbs[0] != crumbs[1]` ложно (обе крошки = «…навесного фасада типового этажа…»).

- [ ] **Step 3: Переписать `_classify_nodes`**

В `backend/app/services/estimate_matching_service.py` добавить в импорт из `app.domain.classification`:

```python
from app.domain.classification import (
    build_embedding_input,
    classify_lexical,
    is_excluded,
    resolve_ancestor_indices,
)
```

Заменить метод `_classify_nodes` целиком на:

```python
    def _classify_nodes(self, estimate_id: int) -> int:
        nodes = self._estimates.fetch_all_nodes(estimate_id)
        if not nodes:
            return 0
        # Позиционный резолв предков (фикс Кейса D): ближайшее предшествующее вхождение кода.
        anc = resolve_ancestor_indices([n.code for n in nodes])
        # Проход 1: лексика. Собственный класс — по id. UNSURE копим (по индексу) для LLM.
        cls_by_id: dict[int, WorkClass] = {}
        unsure_idx: list[int] = []
        for i, n in enumerate(nodes):
            cls = classify_lexical(n.name)
            cls_by_id[n.id] = cls
            if cls is WorkClass.UNSURE:
                unsure_idx.append(i)
        # Проход 1b: LLM по неоднозначным; контекст предков — позиционный.
        if unsure_idx:
            items = [
                NodeToClassify(nodes[i].name, tuple(nodes[j].name for j, _ in anc[i]))
                for i in unsure_idx
            ]
            for i, verdict in zip(unsure_idx, self._classifier.classify(items), strict=True):
                cls_by_id[nodes[i].id] = verdict
        # Проход 2: override (код-based лист + non-org предок) + крошка с выбросом своего org.
        parent_codes = {p for n in nodes if (p := self._parent_of(n.code))}
        results: list[NodeClassification] = []
        for i, n in enumerate(nodes):
            ancestors = [(nodes[j].name, cls_by_id[nodes[j].id]) for j, _ in anc[i]]
            own = cls_by_id[n.id]
            is_leaf = n.code not in parent_codes  # код-based; коллизия — отдельная задача (spec §5)
            has_non_org_anc = any(cls is not WorkClass.ORG for _, cls in ancestors)
            excluded = is_excluded(own, is_leaf=is_leaf, has_non_org_ancestor=has_non_org_anc)
            crumb = build_embedding_input(n.name, ancestors, self_class=own)
            if not excluded and not crumb:
                logger.error(
                    "kept-узел с пустой крошкой: id=%s code=%s class=%s", n.id, n.code, own
                )
                raise AssertionError(f"kept node with empty crumb: {n.id} {n.code} {own}")
            results.append(
                NodeClassification(node_id=n.id, excluded=excluded, embedding_input=crumb)
            )
        self._estimates.save_node_classifications(results)
        return sum(1 for r in results if r.excluded)
```

Удалить ставшие неиспользуемыми методы `_ancestor_codes` и `_ancestor_names`. **Оставить** `_parent_of` (нужен для `parent_codes`/`is_leaf`).

- [ ] **Step 4: Запустить целевой + соседние тесты**

Run: `uv run --directory backend pytest tests/test_estimate_matching_service.py -v`
Expected: PASS, включая новый `test_classify_collision_distinct_breadcrumbs` и прежние (`test_classify_excludes_org_and_strips_breadcrumb`, `test_duplicate_code_excludes_only_scaffold`, rescue-тесты).

- [ ] **Step 5: Линт + коммит**

```bash
uv run --directory backend ruff check app/services/estimate_matching_service.py tests/test_estimate_matching_service.py
git add backend/app/services/estimate_matching_service.py backend/tests/test_estimate_matching_service.py
git commit -m "fix(matching): _classify_nodes резолвит предков позиционно (фикс Кейса D)"
```

---

### Task 3: Интеграция в `estimate_parser` (consistency)

**Files:**
- Modify: `backend/app/services/estimate_parser.py` (импорт + двухфазный `parse`)
- Test: `backend/tests/test_estimate_parser.py` (переопределить дубль-тест + добавить коллизионный)

**Interfaces:**
- Consumes: `resolve_ancestor_indices(codes)` (Task 1).

- [ ] **Step 1: Переопределить дубль-тест и добавить коллизионный**

В `backend/tests/test_estimate_parser.py` заменить `test_duplicate_code_keeps_first_name_and_warns` на:

```python
def test_duplicate_code_uses_nearest_preceding_name() -> None:
    # фикс Кейса D: ребёнок дубля берёт БЛИЖАЙШЕЕ имя предка сверху (Имя-Б), не первое (Имя-А).
    content = _xlsx(
        [
            ("1", "Первый", "СМР"),
            ("1.1", "Имя-А", None),
            ("1.1", "Имя-Б", None),       # дубль кода
            ("1.1.1", "Дитя", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    assert sum(n.code == "1.1" for n in parsed.nodes) == 2          # оба сохранены
    child = next(n for n in parsed.nodes if n.code == "1.1.1")
    assert child.embedding_input == "Первый. Имя-Б. Дитя"           # ближайший предок сверху
    assert any("1.1" in w for w in parsed.warnings)                  # дубль всё ещё логируется
```

И добавить:

```python
def test_breadcrumb_nearest_preceding_on_etap_collision() -> None:
    content = _xlsx(
        [
            ("6", "Устройство фасадов", "СМР"),
            ("6.4", "навесной типового", None),
            ("6.4.1", "подсистема", None),
            ("6.5", "модульный", None),
            ("6.4", "навесной 1 этажа", None),   # код 6.4 повторно
            ("6.4.1", "подсистема", None),        # код 6.4.1 повторно
        ]
    )
    parsed = EstimateParser().parse(content)
    crumbs = [n.embedding_input for n in parsed.nodes if n.code == "6.4.1"]
    assert crumbs == [
        "Устройство фасадов. навесной типового. подсистема",
        "Устройство фасадов. навесной 1 этажа. подсистема",
    ]
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `uv run --directory backend pytest tests/test_estimate_parser.py -k "nearest_preceding or collision" -v`
Expected: FAIL — крошки берут первое имя предка («Имя-А» / «навесной типового» для обеих).

- [ ] **Step 3: Сделать `parse` двухфазным**

В `backend/app/services/estimate_parser.py` добавить импорт:

```python
from app.domain.classification import resolve_ancestor_indices
```

Заменить метод `parse` целиком на (фаза 1 — собрать узлы по порядку без крошки; фаза 2 — резолв + крошка):

```python
    def parse(self, content: bytes) -> ParsedEstimate:
        df = pd.read_excel(
            io.BytesIO(content), engine="openpyxl", dtype={SECTION_NO_COLUMN: str}
        )
        missing = {SECTION_NO_COLUMN, NAME_COLUMN} - set(df.columns)
        if missing:
            raise ValueError(f"В файле отсутствуют обязательные колонки: {sorted(missing)}")

        positions: list[EstimatePosition] = []
        warnings: list[str] = []
        raw: list[dict] = []                      # узлы фазы 1 (без embedding_input)
        name_by_code: dict[str, str] = {}         # только для warning о дубле
        top_type_by_segment: dict[str, str | None] = {}
        last_node_code: str | None = None

        for raw_idx, record in df.iterrows():
            source_index = int(raw_idx)  # type: ignore[arg-type]
            no = record[SECTION_NO_COLUMN]
            name = _clean_name(record[NAME_COLUMN])
            if not name or name.lower() == "nan":
                warnings.append(f"строка {source_index}: пустое имя — пропущена")
                continue
            if pd.isna(no):  # POSITION
                if last_node_code is None:
                    warnings.append(f"строка {source_index}: позиция до первого узла")
                positions.append(EstimatePosition(name, last_node_code, source_index))
                continue
            code = re.sub(r"\s+", "", str(no)).strip(".")
            segments = code.split(".")
            if not code or not all(seg.isdigit() for seg in segments):
                warnings.append(f"строка {source_index}: нечисловой код '{no}' → позиция")
                positions.append(EstimatePosition(name, last_node_code, source_index))
                continue
            depth = len(segments)
            parent_code = ".".join(segments[:-1]) or None
            if code in name_by_code:
                warnings.append(f"строка {source_index}: дубль кода '{code}'")
            else:
                name_by_code[code] = name
            if depth == 1:
                vid = record[SECTION_TYPE_COLUMN] if SECTION_TYPE_COLUMN in df.columns else None
                top_type_by_segment[code] = None if pd.isna(vid) else str(vid).strip()
            raw.append({
                "code": code, "name": name, "parent_code": parent_code,
                "section_type": top_type_by_segment.get(segments[0]),
                "source_index": source_index, "depth": depth,
            })
            last_node_code = code

        # Фаза 2: позиционный резолв предков (фикс Кейса D) + крошка байт-в-байт как раньше.
        codes = [r["code"] for r in raw]
        anc = resolve_ancestor_indices(codes)
        present = set(codes)
        nodes: list[EstimateNode] = []
        for i, r in enumerate(raw):
            for k in range(1, r["depth"]):  # паритет warning о недостающем предке
                ancestor = ".".join(r["code"].split(".")[:k])
                if ancestor not in present:
                    warnings.append(f"строка {r['source_index']}: нет предка '{ancestor}'")
            parts = [raw[j]["name"] for j, _ in anc[i]]
            parts.append(r["name"])
            nodes.append(EstimateNode(
                code=r["code"], name=r["name"], parent_code=r["parent_code"],
                section_type=r["section_type"], embedding_input=". ".join(parts),
                source_index=r["source_index"], depth=r["depth"],
            ))

        return ParsedEstimate(nodes=nodes, positions=positions, warnings=warnings)
```

- [ ] **Step 4: Запустить парсер-тесты целиком**

Run: `uv run --directory backend pytest tests/test_estimate_parser.py -v`
Expected: PASS — новые два теста + прежние (`test_embedding_input_is_ancestors_plus_name_no_descendants`, `test_ancestors_by_segment_not_string_prefix`, `test_source_index_integrity_with_skip_above` без коллизий не меняются).

- [ ] **Step 5: Линт + коммит**

```bash
uv run --directory backend ruff check app/services/estimate_parser.py tests/test_estimate_parser.py
git add backend/app/services/estimate_parser.py backend/tests/test_estimate_parser.py
git commit -m "fix(parser): крошка по ближайшему предшествующему предку (фикс Кейса D)"
```

---

### Task 4: Характеризующий тест `is_leaf` на коллизии (фикс ОТЛОЖЕН)

**Files:**
- Test: `backend/tests/test_estimate_matching_service.py` (добавить один тест)

**Interfaces:** нет (тест фиксирует текущее поведение, кода не меняет).

- [ ] **Step 1: Написать характеризующий тест**

Добавить в `backend/tests/test_estimate_matching_service.py`:

```python
def test_is_leaf_collision_defeats_org_leaf_rescue_current_behavior() -> None:
    # ХАРАКТЕРИЗУЮЩИЙ (не фикс): is_leaf код-based (`code not in parent_codes`), поэтому
    # коллизия кода делает org-ЛИСТ «не-листом» → спасение не срабатывает. «Корпус 8» (реально
    # лист) ошибочно excluded из-за наличия 1.1.1 у тёзки-кода. Фикс is_leaf отложен (spec §5).
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [
        ("1", "Подготовительные работы", None),  # WORK
        ("1.1", "Корпус 8", "1"),                 # ORG, в одиночку был бы спасён (лист под work)
        ("1.1", "Корпус 9", "1"),                 # тот же код 1.1
        ("1.1.1", "Монтаж", "1.1"),               # делает код 1.1 родителем → оба 1.1 «не-лист»
    ])
    svc = _classify_svc(repo, classifier=FakeWorkTypeClassifier(default=WorkClass.WORK))
    svc._classify_nodes(est.id)  # noqa: SLF001
    corp = [r for r in repo.get(est.id, 1, is_admin=True).rows if r.code == "1.1"]
    assert [r.status for r in corp] == ["excluded", "excluded"]  # текущее (несовершенное) поведение
```

- [ ] **Step 2: Запустить — убедиться, что зелено (фиксирует текущее поведение)**

Run: `uv run --directory backend pytest tests/test_estimate_matching_service.py::test_is_leaf_collision_defeats_org_leaf_rescue_current_behavior -v`
Expected: PASS (документирует текущее поведение; если когда-нибудь is_leaf починят — тест станет красным и заставит обновить его осознанно).

- [ ] **Step 3: Коммит**

```bash
git add backend/tests/test_estimate_matching_service.py
git commit -m "test(matching): характеризующий тест is_leaf на коллизии кодов (фикс отложен)"
```

---

### Task 5: Заметка в TECH_DEBT (допущение code-prefix + outline)

**Files:**
- Modify: `docs/TECH_DEBT.md` (в секцию «Кейс D»)

**Interfaces:** нет (документация).

- [ ] **Step 1: Дописать заметку в конец секции «🔴 Кейс D»**

В `docs/TECH_DEBT.md`, сразу после абзаца «**Как чинить:**» в секции Кейса D, добавить:

```markdown
**Достаточность code-prefix (после фикса nearest-preceding, измерено 2026-06-30):** позиционный
резолв чинит главу 6 полностью (0 расхождений по этажу против outline). НО на этой же смете он
недостаточен вне гл.6: гл.10 — 4 узла `10.2.1.x` (наружное освещение ЖК) не имеют предшествующего
`10.2` → откат тянет «фасадные осветительные приборы 2 Этап Офис» из ~113 строк НИЖЕ (контаминация,
но НЕ регрессия — равно старому словарю); гл.11 — `газон` теряет рабочих предков «Озеленение.
Покрытие по грунту» (отдельный режим, не откат). Готовый запасной сигнал — **outline-level**
(`outlineLevel` + стек по уровню): на этих узлах даёт корректную крошку УЖЕ сейчас, проще
nearest-preceding-по-коду. Смена структурного сигнала отложена по скоупу, не из-за неполноценности
outline. См. spec `docs/superpowers/specs/2026-06-30-breadcrumb-ancestor-resolution-design.md`.
```

- [ ] **Step 2: Коммит**

```bash
git add docs/TECH_DEBT.md
git commit -m "docs(tech-debt): Кейс D — допущение code-prefix и outline как запасной сигнал"
```

---

### Task 6: Сквозная проверка + пост-замер (ручной, не CI)

**Files:** нет правок кода; запуск тестов и оффлайн-метрики.

**Interfaces:** нет.

- [ ] **Step 1: Полный прогон тестов**

Run: `uv run --directory backend pytest -q`
Expected: всё зелено (≥306 passed; были 300 + новые тесты), 0 failed.

- [ ] **Step 2: Пост-замер `eval_matching` (нужны проэмбеженный справочник + живой OpenRouter)**

Снять «после» на этой ветке:

Run: `uv run --directory backend python -m app.scripts.eval_matching --benchmark "Смета - образец размеченная до конца" --report after.csv`
Записать top-1 / top-3 группы B.

Для «до» (baseline на старом поведении): `git stash`-нуть нельзя (закоммичено) — переключиться на `main`, прогнать тот же eval, вернуться. Зафиксировать дельту top-1/top-3 в комментарии к PR/девлоге.

- [ ] **Step 3: Именованный срез — 4 узла отката + метрика is_leaf**

Срез отката (`10.2.1.x`) и коллизии is_leaf меряются ad-hoc пробом (как в анализе спека): пройти узлы бенчмарка через `resolve_ancestor_indices`, выбрать узлы с `is_fallback=True` → проверить, флипнул ли их top-1; отдельно посчитать org-листы, ставшие excluded из-за коллизии в `parent_codes`. Результат (числа) записать рядом с дельтой top-1/top-3.

- [ ] **Step 4: Зафиксировать результаты замера**

Дописать измеренные числа (top-1/top-3 до/после, срез отката, is_leaf-коллизии) в девлог `docs/devlog/` или в PR-описание. Коммит:

```bash
git add docs/devlog/
git commit -m "docs(devlog): пост-замер фикса Кейса D (top-1/top-3, срез отката, is_leaf)"
```

---

## После плана

Влить ветку `fix/breadcrumb-ancestor-collision` в `main` (как договаривались — ветка → коммиты → merge, остаться на `main`).
