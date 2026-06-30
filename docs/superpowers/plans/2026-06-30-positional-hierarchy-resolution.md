# Позиционный резолв иерархии сметы (outline-детекция + стек по глубине-кода) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Чинить тихую контаминацию крошки (`embedding_input`) на кривой нумерации «№ раздела» — резолвить предков ПОЗИЦИОННЫМ стеком по глубине-кода (а не усечением кода + первым вхождением), детектить структурные аномалии и показывать их оператору при загрузке.

**Architecture:** Чистые доменные функции (`resolve_ancestor_indices`, `leaf_flags`, `canonical_codes`, `detect_structural_anomalies`) по ГЛУБИНЕ-КОДА (число сегментов): стек смотрит только вверх → forward-ref невозможен, коллизии дублей разводятся, пропущенный уровень даёт ближайшего открытого предка. Три потребителя резолва (`estimate_parser`, `_classify_nodes`, его LLM-контекст) строят крошку по одному механизму. `outline_level` читается парсером ТОЛЬКО для детекции (`outline_overrides` + аномалии), в резолв НЕ идёт (см. врезку «РЕШЕНИЕ РЕВЬЮ v2» в спеке).

**Tech Stack:** Python 3.11+, FastAPI/Clean Architecture, pytest, `uv`, pandas + openpyxl (парсер), pgvector (вне скоупа). Фронт: Vite+React+TS.

**Спек:** [docs/superpowers/specs/2026-06-30-positional-hierarchy-resolution-design.md](../specs/2026-06-30-positional-hierarchy-resolution-design.md) — источник правды.

## Global Constraints

- ruff line-length 100, `target py311`; каждый модуль с `from __future__ import annotations`; type hints обязательны.
- Комментарии/строки — по-русски, как в окружающем коде.
- Юнит-тесты НЕ ходят в реальную БД/AI — только фейки портов ([tests/fakes.py](../../../backend/tests/fakes.py)) и прямые вызовы.
- Команды бэка — строго `uv run` из `backend/`. Не вызывать системный python/pip.
- Файлы в LF. Перед коммитом — `uv run ruff check .`.
- Ветка: `fix/breadcrumb-ancestor-collision`.
- **НЕ ТРОГАТЬ:** org-стрип, порог 0.90, LLM-арбитр, каталог, **схему БД**, экспортный офсет `+2`, `classify_lexical`/LLM-классификатор, `is_excluded`-правило.
- **ВНЕ СКОУПА (§5 спеки):** ремонт нумерации в экспорте (галочка, перезапись `№ раздела`). `canonical_codes` в домене реализуем, но НЕ подключаем к экспорту.
- **`depth` НЕ мутировать** — остаётся `len(segments)` (нужен `reconstruct_nodes`/бенчмарку). Резолв берёт глубину из `len(code.split("."))` на лету, не из нового поля.

## Пять мест, где не наступить (из брифа ревью)

1. **Узлы = только coded-строки.** `depths`/`resolve`/`leaf_flags` — только по coded-узлам; позиции (№=NaN) НЕ входят. В сервисе это само собой (`fetch_all_nodes` отдаёт только строки-узлы); в парсере — позиции в отдельный список.
2. **🔴 Рассинхрон pandas↔openpyxl.** На каждый coded-узел: код openpyxl по `source_index+2` обязан совпасть с кодом pandas по `source_index` (нормализованно, с коэрсингом int-float). Не совпало → `ValueError` ДО записи. Обязательный «грязный» тест.
3. **`depth` не перегружать** — отдельной семантики `structural_depth` не вводим (резолв на глубине-кода, считается из `code`).
4. **`outline_code_mismatch` — агрегат** (`outline_overrides: int`), не построчно (на многоэтапке ~14%).
5. **Глубина = число сегментов кода.** Стек только вверх; `is_fallback`-флага нет.

## Состояние на момент написания плана

Доменный слой (Задачи 1–3) уже реализован по TDD в этой сессии и зелёный (16/17 юнитов; один — `test_leaf_flags_collision_branch` — содержал опечатку в ОЖИДАНИИ, исправляется в Задаче 1, шаг 1). Задачи 4–8 — впереди.

## File Structure

- `backend/app/domain/entities.py` — `StructuralAnomaly`; `ParsedEstimate` +`anomalies`/`outline_overrides`. **[готово]**
- `backend/app/domain/classification.py` — `resolve_ancestor_indices`, `leaf_flags`, `canonical_codes`, `detect_structural_anomalies`, `_parent_code`. **[готово]**
- `backend/tests/test_hierarchy.py` — юниты домена. **[готово, 1 правка]**
- `backend/app/services/estimate_parser.py` — openpyxl-проход (outline + код для ассерта), позиционная крошка, аномалии.
- `backend/tests/test_estimate_parser.py` — правка collision-теста + новые (outline/alignment/dirty/anomaly).
- `backend/app/services/estimate_matching_service.py` — `_classify_nodes`/LLM-контекст/`is_leaf` на позиционный резолв.
- `backend/tests/test_estimate_matching_service.py` — collision-сервис-тест (разная крошка).
- `backend/app/services/estimate_service.py` — `IngestResult` +`anomalies`/`outline_overrides`.
- `backend/app/api/schemas.py` — `EstimateUploadResponse` +поля.
- `backend/app/api/routes/estimates.py` — проброс в ответ.
- `backend/tests/test_estimates_api.py` (или существующий API-тест) — ответ загрузки содержит аномалии.
- `frontend/src/pages/estimate/…` — блок «Структура сметы».
- Пост-замер: `just eval-matching`, запись результата в devlog/TECH_DEBT.

---

### Task 1: Домен — позиционный резолв (`resolve_ancestor_indices` + `leaf_flags`)

**Files:**
- Modify: `backend/app/domain/classification.py`
- Test: `backend/tests/test_hierarchy.py`

**Interfaces:**
- Produces: `resolve_ancestor_indices(depths: Sequence[int]) -> list[list[int]]` (для каждого i — индексы предков root→parent, строго возрастают, `< i`); `leaf_flags(depths: Sequence[int]) -> list[bool]`.

- [ ] **Step 1: Исправить опечатку ожидания в `test_leaf_flags_collision_branch`**

В [test_hierarchy.py](../../../backend/tests/test_hierarchy.py) ожидание противоречит комментарию (B не лист → должно быть `False`). Правильное:

```python
def test_leaf_flags_collision_branch() -> None:
    # A(1) B(2) C(3) D(2) E(3): B не лист (есть C), D не лист (есть E), C/E листья.
    assert leaf_flags([1, 2, 3, 2, 3]) == [False, False, True, False, True]
```

- [ ] **Step 2: Прогнать тесты резолва — убедиться, что зелёные**

Run: `uv run pytest tests/test_hierarchy.py -q -k "resolve or leaf"`
Expected: PASS (функции уже реализованы).

- [ ] **Step 3: Реализация (уже в дереве — сверить)**

```python
def resolve_ancestor_indices(depths: Sequence[int]) -> list[list[int]]:
    stack: list[tuple[int, int]] = []  # (depth, index) открытых предков
    result: list[list[int]] = []
    for i, d in enumerate(depths):
        while stack and stack[-1][0] >= d:
            stack.pop()
        result.append([idx for _, idx in stack])
        stack.append((d, i))
    return result


def leaf_flags(depths: Sequence[int]) -> list[bool]:
    n = len(depths)
    return [i == n - 1 or depths[i + 1] <= depths[i] for i in range(n)]
```

- [ ] **Step 4: Прогнать весь файл**

Run: `uv run pytest tests/test_hierarchy.py -q`
Expected: PASS (включая property-монотонность).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/classification.py backend/app/domain/entities.py backend/tests/test_hierarchy.py
git commit -m "feat(domain): позиционный резолв предков по глубине-кода + leaf_flags"
```

---

### Task 2: Домен — `canonical_codes`

**Files:**
- Modify: `backend/app/domain/classification.py`
- Test: `backend/tests/test_hierarchy.py`

**Interfaces:**
- Consumes: `resolve_ancestor_indices`.
- Produces: `canonical_codes(depths: Sequence[int]) -> list[str]` — `1/1.1/1.1.1` из восстановленного дерева; пропущенные уровни схлопываются. Потребитель — экспорт (отдельный патч), здесь только домен+юниты.

- [ ] **Step 1: Тесты (уже в test_hierarchy.py — сверить)**

```python
def test_canonical_simple_tree() -> None:
    assert canonical_codes([1, 2, 3]) == ["1", "1.1", "1.1.1"]
    assert canonical_codes([1, 2, 2, 1]) == ["1", "1.1", "1.2", "2"]

def test_canonical_compresses_missing_levels() -> None:
    assert canonical_codes([2, 3, 5]) == ["1", "1.1", "1.1.1"]

def test_canonical_collision() -> None:
    assert canonical_codes([1, 2, 3, 2, 3]) == ["1", "1.1", "1.1.1", "1.2", "1.2.1"]
```

- [ ] **Step 2: Прогон — RED, если функции нет; иначе сверить GREEN**

Run: `uv run pytest tests/test_hierarchy.py -q -k canonical`
Expected: PASS.

- [ ] **Step 3: Реализация (в дереве — сверить)**

```python
def canonical_codes(depths: Sequence[int]) -> list[str]:
    chains = resolve_ancestor_indices(depths)
    child_count: dict[int | None, int] = {}
    codes: list[str] = []
    for chain in chains:
        parent = chain[-1] if chain else None
        child_count[parent] = child_count.get(parent, 0) + 1
        prefix = codes[parent] + "." if parent is not None else ""
        codes.append(prefix + str(child_count[parent]))
    return codes
```

- [ ] **Step 4: Прогон** — `uv run pytest tests/test_hierarchy.py -q -k canonical` → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(domain): canonical_codes из позиционного дерева"`.

---

### Task 3: Домен — `StructuralAnomaly` + `detect_structural_anomalies`

**Files:**
- Modify: `backend/app/domain/entities.py`, `backend/app/domain/classification.py`
- Test: `backend/tests/test_hierarchy.py`

**Interfaces:**
- Produces: `StructuralAnomaly(kind, source_index, code, name, detail)` (frozen); `detect_structural_anomalies(rows: Sequence[tuple[int, str, str, int]]) -> tuple[list[StructuralAnomaly], int]`. `rows` = `(source_index, code, name, outline_level)` coded-узлов в порядке документа. Возвращает построчные аномалии (`duplicate_code`/`parent_below`/`parent_missing`/`depth_jump`) и агрегат `outline_overrides`.

- [ ] **Step 1: Тесты (в test_hierarchy.py — сверить)** — `duplicate_code` (оба вхождения), `parent_below`, `parent_missing`, `depth_jump`, агрегат `outline_overrides==2` без построчного `outline_code_mismatch`, чистый вход → `([], 0)`.
- [ ] **Step 2: Прогон** — `uv run pytest tests/test_hierarchy.py -q -k "detect or outline or clean"` → PASS.
- [ ] **Step 3: Реализация (в дереве — сверить).** `StructuralAnomaly` в entities; `detect_structural_anomalies` + `_parent_code` в classification (как реализовано). outline_code_mismatch только инкрементит `overrides`, в список НЕ кладётся.
- [ ] **Step 4: Прогон всего файла** — `uv run pytest tests/test_hierarchy.py -q` → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(domain): детектор структурных аномалий + outline_overrides"`.

---

### Task 4: Парсер — outline-проход, ассерт выравнивания, позиционная крошка, аномалии

**Files:**
- Modify: `backend/app/services/estimate_parser.py`
- Test: `backend/tests/test_estimate_parser.py`

**Interfaces:**
- Consumes: `resolve_ancestor_indices`, `detect_structural_anomalies` (домен).
- Produces: `EstimateParser.parse(content) -> ParsedEstimate` с заполненными `anomalies` и `outline_overrides`; крошка узлов строится позиционно.

- [ ] **Step 1: Правка collision-теста + новые падающие тесты**

В [test_estimate_parser.py](../../../backend/tests/test_estimate_parser.py) заменить `test_duplicate_code_keeps_first_name_and_warns` (он кодирует СТАРОЕ first-occurrence) на позиционное ожидание и добавить новые:

```python
def test_duplicate_code_uses_nearest_preceding_parent() -> None:
    # Позиционный резолв: ребёнок берёт БЛИЖАЙШЕГО предшествующего предка, не первое вхождение.
    content = _xlsx(
        [
            ("1", "Первый", "СМР"),
            ("1.1", "Имя-А", None),
            ("1.1", "Имя-Б", None),       # дубль кода — ближайший предок для следующего
            ("1.1.1", "Дитя", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    child = next(n for n in parsed.nodes if n.code == "1.1.1")
    assert child.embedding_input == "Первый. Имя-Б. Дитя"   # было «Имя-А» (первое вхождение)
    assert any(a.kind == "duplicate_code" for a in parsed.anomalies)


def test_parent_below_does_not_pull_context_from_below() -> None:
    # «родитель ниже»: ребёнок 10.2.1 встречается ВЫШЕ строки-родителя 10.2 →
    # позиционный стек НЕ тянет имя снизу (forward-ref невозможен).
    content = _xlsx(
        [
            ("10", "Инженерные системы", "СМР"),
            ("10.1", "Освещение ЖК", None),
            ("10.1.1", "Монтаж опор", None),     # предок в документе — «Освещение ЖК»
            ("10.2", "Освещение Офис", None),    # код-родитель 10.1.1? нет; здесь просто следом
        ]
    )
    parsed = EstimateParser().parse(content)
    node = next(n for n in parsed.nodes if n.code == "10.1.1")
    assert node.embedding_input == "Инженерные системы. Освещение ЖК. Монтаж опор"


def test_outline_overrides_zero_on_flat_file() -> None:
    # df.to_excel не создаёт группировку → file_has_outline False → overrides 0.
    content = _xlsx([("1", "Раздел", "СМР"), ("1.1", "Под", None)])
    parsed = EstimateParser().parse(content)
    assert parsed.outline_overrides == 0


def test_alignment_assert_catches_desync() -> None:
    # «Грязный» файл: openpyxl видит лишнюю строку, которой нет во фрейме pandas в той же позиции
    # → код по source_index+2 разойдётся с pandas → ValueError. Строим .xlsx вручную (openpyxl),
    # вставляя пустую строку-разделитель так, чтобы сместить физические строки.
    import io as _io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([_NO, _NAME, _TYPE])
    ws.append(["1", "Раздел", "СМР"])
    ws.append([None, None, None])          # полностью пустая физ.строка
    ws.append(["1.1", "Подраздел", None])
    buf = _io.BytesIO(); wb.save(buf)
    # pandas роняет полностью пустую строку из data? Нет — read_excel сохраняет её как NaN-строку,
    # поэтому здесь выравнивание ДЕРЖИТСЯ. Для срыва нужен иной механизм: см. ниже.
```

> **Замечание реализатору:** подобрать сценарий рассинхрона эмпирически. pandas `read_excel` по умолчанию сохраняет пустые строки как NaN (RangeIndex не сдвигается), поэтому простая пустая строка НЕ рвёт выравнивание. Рабочий «грязный» кейс: лист, где физическая строка существует в openpyxl, но pandas её отбрасывает (напр. строка целиком из формульных/пустых ячеек выше первой данных, или `header`-смещение). Реализатор ОБЯЗАН довести тест до состояния, в котором БЕЗ ассерта крошка строилась бы по сдвинутому outline, а ассерт ловит это `ValueError`. Если эмпирически сорвать выравнивание тем же `read_excel`-контрактом не удаётся (pandas и openpyxl видят строки одинаково), это само по себе вывод: одиночный риск-класс закрыт контрактом — тогда тест фиксирует, что ассерт стоит и НЕ ложно-срабатывает на чистом файле, а «грязный» сценарий документируется как недостижимый при текущем чтении. Не выдумывать срыв, которого нет.

- [ ] **Step 2: Прогон — RED**

Run: `uv run pytest tests/test_estimate_parser.py -q`
Expected: FAIL (новые тесты; старое поведение крошки = «Имя-А», `anomalies`/`outline_overrides` отсутствуют).

- [ ] **Step 3: Реализация парсера**

Переписать `EstimateParser.parse` ([estimate_parser.py](../../../backend/app/services/estimate_parser.py)):

```python
from openpyxl import load_workbook
from app.domain.classification import detect_structural_anomalies, resolve_ancestor_indices


def _norm_code(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():  # openpyxl numeric cell 1.0 → "1"
        value = int(value)
    code = re.sub(r"\s+", "", str(value)).strip(".")
    return code or None


class EstimateParser:
    def parse(self, content: bytes) -> ParsedEstimate:
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl", dtype={SECTION_NO_COLUMN: str})
        missing = {SECTION_NO_COLUMN, NAME_COLUMN} - set(df.columns)
        if missing:
            raise ValueError(f"В файле отсутствуют обязательные колонки: {sorted(missing)}")

        outline_by_si, code_by_si = self._read_outline(content)
        file_has_outline = max(outline_by_si.values(), default=0) >= 1  # резолв НЕ использует

        warnings: list[str] = []
        positions: list[EstimatePosition] = []
        last_node_code: str | None = None
        # coded-узлы (только они идут в стек глубины) — собираем в порядке документа
        coded: list[dict] = []   # {source_index, code, name, segments, section_type, outline}
        top_type_by_segment: dict[str, str | None] = {}

        for raw_idx, record in df.iterrows():
            si = int(raw_idx)  # type: ignore[arg-type]
            no = record[SECTION_NO_COLUMN]
            name = _clean_name(record[NAME_COLUMN])
            if not name or name.lower() == "nan":
                warnings.append(f"строка {si}: пустое имя — пропущена")
                continue
            if pd.isna(no):
                if last_node_code is None:
                    warnings.append(f"строка {si}: позиция до первого узла")
                positions.append(EstimatePosition(name, last_node_code, si))
                continue
            code = re.sub(r"\s+", "", str(no)).strip(".")
            segments = code.split(".")
            if not code or not all(seg.isdigit() for seg in segments):
                warnings.append(f"строка {si}: нечисловой код '{no}' → позиция")
                positions.append(EstimatePosition(name, last_node_code, si))
                continue
            # 🔴 АССЕРТ ВЫРАВНИВАНИЯ pandas↔openpyxl на каждый coded-узел
            if _norm_code(code_by_si.get(si)) != code:
                raise ValueError(
                    f"рассинхрон pandas↔openpyxl на строке {si}: "
                    f"pandas='{code}' openpyxl='{_norm_code(code_by_si.get(si))}'"
                )
            if len(segments) == 1:
                vid = record[SECTION_TYPE_COLUMN] if SECTION_TYPE_COLUMN in df.columns else None
                top_type_by_segment[code] = None if pd.isna(vid) else str(vid).strip()
            coded.append({
                "source_index": si, "code": code, "name": name, "segments": segments,
                "section_type": top_type_by_segment.get(segments[0]),
                "outline": outline_by_si.get(si, 0),
            })
            last_node_code = code

        depths = [len(c["segments"]) for c in coded]
        chains = resolve_ancestor_indices(depths)
        nodes: list[EstimateNode] = []
        for i, c in enumerate(coded):
            parts = [coded[j]["name"] for j in chains[i]]
            parts.append(c["name"])
            embedding_input = ". ".join(parts)  # байт-в-байт как template_parser
            nodes.append(EstimateNode(
                code=c["code"], name=c["name"],
                parent_code=".".join(c["segments"][:-1]) or None,  # код-based, не трогаем
                section_type=c["section_type"], embedding_input=embedding_input,
                source_index=c["source_index"], depth=len(c["segments"]),
            ))

        anomalies, overrides = detect_structural_anomalies(
            [(c["source_index"], c["code"], c["name"], c["outline"]) for c in coded]
        )
        return ParsedEstimate(nodes=nodes, positions=positions, warnings=warnings,
                              anomalies=anomalies, outline_overrides=overrides)

    @staticmethod
    def _read_outline(content: bytes) -> tuple[dict[int, int], dict[int, object]]:
        wb = load_workbook(io.BytesIO(content))  # НЕ read_only: нужен row_dimensions.outline_level
        ws = wb.active
        header = [cell.value for cell in ws[1]]
        try:
            col = header.index(SECTION_NO_COLUMN) + 1
        except ValueError:  # pandas уже бы упал; перестраховка
            return {}, {}
        outline_by_si: dict[int, int] = {}
        code_by_si: dict[int, object] = {}
        for er in range(2, ws.max_row + 1):
            si = er - 2
            outline_by_si[si] = ws.row_dimensions[er].outline_level
            code_by_si[si] = ws.cell(row=er, column=col).value
        return outline_by_si, code_by_si
```

- [ ] **Step 4: Прогон**

Run: `uv run pytest tests/test_estimate_parser.py -q`
Expected: PASS (включая golden-skip и numeric-dtype). Если `test_dtype_numeric_code_read_as_string` упал на ассерте — `_norm_code` чинит (int-float коэрсинг).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/estimate_parser.py backend/tests/test_estimate_parser.py
git commit -m "feat(parser): outline-проход + ассерт выравнивания + позиционная крошка + аномалии"
```

---

### Task 5: Сервис матчинга — позиционный `_classify_nodes`, LLM-контекст, `is_leaf`

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py`
- Test: `backend/tests/test_estimate_matching_service.py`

**Interfaces:**
- Consumes: `resolve_ancestor_indices`, `leaf_flags` (домен); `fetch_all_nodes` (порядок по `source_index`).
- Produces: `_classify_nodes` строит крошку позиционно; `is_leaf` из `leaf_flags`; устаревшие `_ancestor_codes`/`_parent_of`/`_ancestor_names` удалены.

- [ ] **Step 1: Падающий сервис-тест на коллизию**

В [test_estimate_matching_service.py](../../../backend/tests/test_estimate_matching_service.py):

```python
def test_classify_collision_gives_different_breadcrumbs() -> None:
    repo = FakeEstimateRepository()
    articles = FakeRepository(candidates=[])
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [
            EstimateNode("6", "Фасады", None, "СМР", "Фасады", 0, 1),
            EstimateNode("6.1", "навесной типового", "6", None, "x", 1, 2),
            EstimateNode("6.1.1", "подсистема", "6.1", None, "x", 2, 3),
            EstimateNode("6.1", "навесной 1 этажа", "6", None, "x", 3, 2),   # дубль кода 6.1
            EstimateNode("6.1.1", "подсистема", "6.1", None, "x", 4, 3),     # дубль кода 6.1.1
        ],
    )
    svc = _classify_service(repo, articles)
    svc._classify_nodes(est.id)  # noqa: SLF001
    rows = sorted(repo.get(est.id, 1, is_admin=True).rows, key=lambda r: r.source_index)
    # два «6.1.1» (si=2 и si=4) — РАЗНЫЕ крошки (сегодня были бы байт-в-байт одинаковы)
    assert rows[2].embedding_input == "Фасады. навесной типового. подсистема"
    assert rows[4].embedding_input == "Фасады. навесной 1 этажа. подсистема"
```

- [ ] **Step 2: Прогон — RED**

Run: `uv run pytest tests/test_estimate_matching_service.py::test_classify_collision_gives_different_breadcrumbs -v`
Expected: FAIL (обе крошки = «Фасады. навесной типового. подсистема» — первое вхождение).

- [ ] **Step 3: Реализация — переписать `_classify_nodes`**

Заменить тело (строки ~122–175) на позиционный резолв; удалить `name_by_code`/`repr_id_by_code`/`parent_codes`/`_ancestor_codes`/`_parent_of`/`_ancestor_names`:

```python
def _classify_nodes(self, estimate_id: int) -> int:
    nodes = self._estimates.fetch_all_nodes(estimate_id)  # порядок по source_index
    if not nodes:
        return 0
    depths = [len(n.code.split(".")) for n in nodes]
    chains = resolve_ancestor_indices(depths)
    leafs = leaf_flags(depths)
    # Проход 1: лексика.
    cls_by_id: dict[int, WorkClass] = {}
    unsure_idx: list[int] = []
    for i, n in enumerate(nodes):
        cls = classify_lexical(n.name)
        cls_by_id[n.id] = cls
        if cls is WorkClass.UNSURE:
            unsure_idx.append(i)
    # Проход 1b: LLM по UNSURE — контекст предков из позиционной цепочки.
    if unsure_idx:
        items = [
            NodeToClassify(nodes[i].name, tuple(nodes[j].name for j in chains[i]))
            for i in unsure_idx
        ]
        verdicts = self._classifier.classify(items)
        for i, verdict in zip(unsure_idx, verdicts, strict=True):
            cls_by_id[nodes[i].id] = verdict
    # Проход 2: override + крошка → bulk.
    results: list[NodeClassification] = []
    for i, n in enumerate(nodes):
        ancestors = [(nodes[j].name, cls_by_id[nodes[j].id]) for j in chains[i]]
        own = cls_by_id[n.id]
        has_non_org_anc = any(cls is not WorkClass.ORG for _, cls in ancestors)
        excluded = is_excluded(own, is_leaf=leafs[i], has_non_org_ancestor=has_non_org_anc)
        crumb = build_embedding_input(n.name, ancestors, self_class=own)
        if not excluded and not crumb:
            logger.error("kept-узел с пустой крошкой: id=%s code=%s class=%s", n.id, n.code, own)
            raise AssertionError(f"kept node with empty crumb: {n.id} {n.code} {own}")
        results.append(NodeClassification(node_id=n.id, excluded=excluded, embedding_input=crumb))
    self._estimates.save_node_classifications(results)
    return sum(1 for r in results if r.excluded)
```

Добавить импорт: `from app.domain.classification import (..., leaf_flags, resolve_ancestor_indices)`.

- [ ] **Step 4: Прогон файла**

Run: `uv run pytest tests/test_estimate_matching_service.py -q`
Expected: PASS (новый collision-тест + существующие `test_classify_excludes_org_and_strips_breadcrumb`, `test_llm_org_verdict_on_mixed_also_excludes`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/estimate_matching_service.py backend/tests/test_estimate_matching_service.py
git commit -m "feat(matching): позиционный резолв предков + is_leaf в _classify_nodes"
```

---

### Task 6: Проброс аномалий и `outline_overrides` в ответ загрузки

**Files:**
- Modify: `backend/app/services/estimate_service.py`, `backend/app/api/schemas.py`, `backend/app/api/routes/estimates.py`
- Test: `backend/tests/test_estimates_api.py` (или существующий API-тест загрузки — найти по `EstimateUploadResponse`)

**Interfaces:**
- Consumes: `ParsedEstimate.anomalies`, `ParsedEstimate.outline_overrides`.
- Produces: `IngestResult` +`anomalies: list[StructuralAnomaly]`/`outline_overrides: int`; `EstimateUploadResponse` +`anomalies`/`outline_overrides`.

- [ ] **Step 1: Падающий API-тест**

```python
def test_upload_response_carries_anomalies_and_outline_overrides(client, auth_headers) -> None:
    # .xlsx с дублем кода → ответ содержит построчную аномалию duplicate_code
    content = _make_xlsx([("1", "A", "СМР"), ("1.1", "B", None), ("1.1", "C", None)])
    resp = client.post("/api/estimates", files={"file": ("e.xlsx", content, _XLSX_MIME)},
                       headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert any(a["kind"] == "duplicate_code" for a in body["anomalies"])
    assert "outline_overrides" in body
```

(Реализатор: использовать существующие фикстуры `client`/`auth_headers`/`_make_xlsx` из текущего API-теста загрузки; не плодить новые.)

- [ ] **Step 2: Прогон — RED** (`KeyError: 'anomalies'`).

- [ ] **Step 3: Реализация — три правки**

`estimate_service.py` — `IngestResult` + проброс:

```python
@dataclass(frozen=True, slots=True)
class IngestResult:
    estimate: Estimate
    positions_count: int
    warnings: list[str]
    anomalies: list[StructuralAnomaly]
    outline_overrides: int
```
```python
        return IngestResult(
            estimate=estimate,
            positions_count=len(parsed.positions),
            warnings=parsed.warnings,
            anomalies=parsed.anomalies,
            outline_overrides=parsed.outline_overrides,
        )
```
(импорт `StructuralAnomaly` из `app.domain.entities`.)

`schemas.py` — DTO:

```python
class StructuralAnomalyOut(BaseModel):
    kind: str
    source_index: int
    code: str
    name: str
    detail: str


class EstimateUploadResponse(BaseModel):
    id: int
    status: str
    nodes_count: int
    positions_count: int
    warnings: list[str]
    anomalies: list[StructuralAnomalyOut] = []
    outline_overrides: int = 0
```

`routes/estimates.py` — проброс:

```python
    return EstimateUploadResponse(
        id=result.estimate.id,
        status=result.estimate.status,
        nodes_count=len(result.estimate.rows),
        positions_count=result.positions_count,
        warnings=result.warnings,
        anomalies=[StructuralAnomalyOut(**vars(a)) for a in result.anomalies],
        outline_overrides=result.outline_overrides,
    )
```

- [ ] **Step 4: Прогон** — `uv run pytest tests/test_estimates_api.py -q` → PASS. Проверить, что прочие вызовы `IngestResult(...)` в тестах/коде обновлены (grep `IngestResult(`).

- [ ] **Step 5: Commit** — `git commit -am "feat(api): аномалии структуры + outline_overrides в ответе загрузки"`.

---

### Task 7: Фронт — блок «Структура сметы»

**Files:**
- Modify: компонент результата загрузки в `frontend/src/pages/estimate/` (найти по использованию `warnings`/типу ответа загрузки), `frontend/src/lib/api/` (тип ответа).
- Test: `frontend` vitest рядом с компонентом.

**Interfaces:**
- Consumes: поле ответа `anomalies: {kind,source_index,code,name,detail}[]`, `outline_overrides: number`.

- [ ] **Step 1: Падающий vitest** — рендер компонента с `anomalies=[{kind:'duplicate_code',...}]` и `outline_overrides=115` показывает заголовок «Структура сметы: 1 замечание» (или N), таблицу с `detail`, и агрегатную строку «в 115 строк(ах) вложенность взята из группировки».
- [ ] **Step 2: Прогон — RED** (`cd frontend && npm run test -- <file>`).
- [ ] **Step 3: Реализация** — расширить тип ответа загрузки в `lib/api/` (`anomalies`, `outline_overrides`); добавить сворачиваемый блок: таблица построчных аномалий (kind/код/имя/detail) + строка-агрегат про outline (показывать, только если `outline_overrides>0`). Если `anomalies` пуст и `outline_overrides===0` — блок не рендерить.
- [ ] **Step 4: Прогон** — vitest PASS; `cd frontend && npm run typecheck` чист.
- [ ] **Step 5: Commit** — `git commit -am "feat(front): блок «Структура сметы» (аномалии + агрегат outline)"`.

---

### Task 8: Верификация сьюта + пост-замер (подтверждение дерева)

**Files:** нет правок кода; запись результата — devlog/TECH_DEBT.

- [ ] **Step 1: Полный бэк-сьют** — `cd backend && uv run pytest -q` → всё зелёное (проверить, что правка `_classify_nodes` не уронила др. тесты; `test_benchmark_reconstruct` зелёный — `depth` не мутировали).
- [ ] **Step 2: ruff** — `cd backend && uv run ruff check .` → чисто. Фронт: `cd frontend && npm run lint`.
- [ ] **Step 3: Пост-замер (разово, OpenRouter живой).** `just embed-worker --once` при необходимости; затем `just eval-matching benchmark=1` ДО — уже снят как baseline? Снять ПОСЛЕ. Зафиксировать дельту top-1/top-3, число узлов с изменённым предком (ожидаем ≈50, не 68 — резолв на глубине-кода), и **отдельно** счётчик `outline_overrides` парсингом золотого файла напрямую (ожидаем ≈115). Срез по `10.2.1.x` (родитель ниже) и газону `11.3.1.1.x` — флипнул ли top-1.
- [ ] **Step 4: Запись** — результат пост-замера в [docs/devlog/](../../devlog/) (новый файл) + перенести «Кейс D» в «Погашено» в [TECH_DEBT.md](../../TECH_DEBT.md) по факту (после мерджа). Зафиксировать: дерево подтверждено → предусловие §5 (экспорт-ремонт) выполнено.
- [ ] **Step 5: Commit** — `git commit -am "docs(devlog): пост-замер позиционного резолва (top-1/top-3, срез 10.2.1/газон)"`.

---

## Self-Review

- **Покрытие спеки:** §2 резолв → Task 1; `canonical_codes` (§5-домен) → Task 2; §4 детекция → Task 3 (домен) + Task 6 (API) + Task 7 (фронт); §3.2 парсер+ассерт → Task 4; §3.3/§3.4 три точки+is_leaf → Task 4/5; §6 пост-замер → Task 8. §5 экспорт-ремонт — сознательно вне скоупа (только `canonical_codes` в домене).
- **Плейсхолдеры:** код приведён в каждом шаге; «грязный» тест (Task 4 Step 1) намеренно оставлен как эмпирическая задача реализатору с явной границей («не выдумывать срыв, которого нет») — это не placeholder, а честная инструкция, т.к. достижимость рассинхрона зависит от read_excel-контракта.
- **Согласованность типов:** `resolve_ancestor_indices(depths)->list[list[int]]`, `leaf_flags(depths)->list[bool]`, `canonical_codes(depths)->list[str]`, `detect_structural_anomalies(rows)->(list[StructuralAnomaly],int)`, `StructuralAnomaly(kind,source_index,code,name,detail)` — имена и сигнатуры совпадают во всех задачах и в коде домена.
