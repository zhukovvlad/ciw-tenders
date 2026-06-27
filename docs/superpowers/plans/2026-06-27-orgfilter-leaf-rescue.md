# Org-фильтр: спасение work-листьев под work-предком — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перестать молчаливо исключать листовые org-узлы («Корпус 8»/«Этап 1») под work-предком — оставлять их и матчить по чистому work-контексту, не трогая `classify_lexical`/LLM.

**Architecture:** Структурный override ПОСЛЕ классификации в `EstimateMatchingService._classify_nodes`: узел `ORG` оставляем ⟺ он код-based лист И имеет non-org предка; крошку строим с выбросом собственного org-токена. Две чистые доменные функции (`is_excluded`, расширенный `build_embedding_input`) + интеграция в сервис. Замер — ре-прогон eval-харнесса.

**Tech Stack:** Python 3.11+, SQLAlchemy, pytest, фейки портов. `uv` из `backend/`.

**Спека:** [docs/superpowers/specs/2026-06-27-orgfilter-leaf-rescue-design.md](../specs/2026-06-27-orgfilter-leaf-rescue-design.md).

## Global Constraints

- ruff line-length 100, target py311, `from __future__ import annotations` в каждом модуле, type hints обязательны.
- Доменный слой (`app/domain/classification.py`) — БЕЗ импортов SQLAlchemy/FastAPI/SDK. Чистые функции.
- Бэкенд строго через `uv run` из `backend/`. Кириллица в stdout → `PYTHONIOENCODING=utf-8` на pytest.
- Юнит/сервис-тесты не ходят в реальную БД/AI — фейки портов ([tests/fakes.py](../../../backend/tests/fakes.py)). Исключение — Task 3 (живой замер, гоняет контроллер).
- `WorkClass` ∈ {WORK, ORG, UNSURE}; UNSURE — финальный keep-класс. `excluded ⟺ own_class is ORG` ЗАМЕНЯЕТСЯ правилом из спеки.
- Несущее для инварианта 2: `ancestors` в `_classify_nodes` — полный список `(name, cls)` по всем предкам БЕЗ предварительной фильтрации ORG (фильтр живёт внутри `has_non_org_ancestor` и `build_embedding_input`).
- **Класс предка под дублями кода — по представителю «первое вхождение».** `name_by_code`/`repr_id_by_code` (существующие структуры прохода 1, строятся `setdefault`) дают для кода предка имя и id ПЕРВОГО вхождения; класс предка = `cls_by_id[repr_id_by_code[a]]`. Под дублями кода-предка с разными классами берётся первое вхождение (та же политика, что для имени) — это та же неоднозначность кода-ключа, что в харнессе; зафиксирована явно, не на `dict`-порядок. На бенчмарке не стреляет (дубли-предки однородны по классу), но политика именно такая.

---

### Task 1: Доменные функции — `build_embedding_input(+self_class)` и `is_excluded`

**Files:**
- Modify: `backend/app/domain/classification.py`
- Test: `backend/tests/test_classification.py` (существует — добавить тесты)

**Interfaces:**
- Produces:
  - `build_embedding_input(self_name, ancestors, *, self_class: WorkClass = WorkClass.WORK, separator=". ", collapse_repeats=True) -> str` — если `self_class is WorkClass.ORG`, собственное имя НЕ добавляется в крошку (как ORG-предки). Дефолт `WORK` → существующие вызовы не меняются.
  - `is_excluded(own_class: WorkClass, *, is_leaf: bool, has_non_org_ancestor: bool) -> bool` — `False` для не-ORG; для ORG `True`, КРОМЕ `is_leaf and has_non_org_ancestor`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `backend/tests/test_classification.py`:

```python
from app.domain.classification import build_embedding_input, is_excluded
from app.domain.entities import WorkClass


def test_build_embedding_input_drops_self_when_org():
    crumb = build_embedding_input(
        "Корпус 8", [("Гидроизоляция фундаментной плиты", WorkClass.WORK)], self_class=WorkClass.ORG
    )
    assert crumb == "Гидроизоляция фундаментной плиты"  # своё org-имя выброшено


def test_build_embedding_input_keeps_self_by_default():
    crumb = build_embedding_input("Монтаж", [("Раздел", WorkClass.WORK)])
    assert crumb == "Раздел. Монтаж"  # дефолт self_class=WORK — поведение прежнее


def test_build_embedding_input_empty_when_all_org_including_self():
    crumb = build_embedding_input("Корпус 8", [("1 Этап ЖК", WorkClass.ORG)], self_class=WorkClass.ORG)
    assert crumb == ""


def test_build_embedding_input_keeps_unsure_ancestor_and_self():
    crumb = build_embedding_input("Лифты", [("Раздел", WorkClass.UNSURE)], self_class=WorkClass.WORK)
    assert crumb == "Раздел. Лифты"  # UNSURE-предок остаётся (фильтруется только ORG)


def test_is_excluded_org_leaf_with_non_org_ancestor_kept():
    assert is_excluded(WorkClass.ORG, is_leaf=True, has_non_org_ancestor=True) is False


def test_is_excluded_org_nonleaf_excluded():
    assert is_excluded(WorkClass.ORG, is_leaf=False, has_non_org_ancestor=True) is True


def test_is_excluded_org_leaf_without_non_org_ancestor_excluded():
    assert is_excluded(WorkClass.ORG, is_leaf=True, has_non_org_ancestor=False) is True


def test_is_excluded_work_and_unsure_kept():
    assert is_excluded(WorkClass.WORK, is_leaf=True, has_non_org_ancestor=False) is False
    assert is_excluded(WorkClass.UNSURE, is_leaf=False, has_non_org_ancestor=False) is False
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend; PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_excluded'` (и/или `build_embedding_input` не принимает `self_class`).

- [ ] **Step 3: Расширить `build_embedding_input`**

В `backend/app/domain/classification.py` заменить сигнатуру/тело `build_embedding_input` на:

```python
def build_embedding_input(
    self_name: str,
    ancestors: list[tuple[str, WorkClass]],
    *,
    self_class: WorkClass = WorkClass.WORK,
    separator: str = ". ",
    collapse_repeats: bool = True,
) -> str:
    """Крошка root→узел; ORG-предки выброшены (справочник org-free, не загрязняем вектор).
    Если узел сам ORG (self_class=ORG) — его собственное имя тоже выброшено (спасённый org-лист
    эмбедится по чистому work-контексту предков)."""
    parts = [_normalize_ws(name) for name, cls in ancestors if cls is not WorkClass.ORG]
    if self_class is not WorkClass.ORG:
        parts.append(_normalize_ws(self_name))
    if collapse_repeats:
        parts = _collapse_consecutive(parts)
    return separator.join(parts)
```

- [ ] **Step 4: Добавить `is_excluded`**

В `backend/app/domain/classification.py` после `classify_lexical` добавить:

```python
def is_excluded(own_class: WorkClass, *, is_leaf: bool, has_non_org_ancestor: bool) -> bool:
    """Решение exclude/keep с учётом структуры дерева. ORG исключаем, КРОМЕ листа с non-org
    предком (работа, разбитая по корпусам/этапам, чьё имя совпало с оргтокеном)."""
    if own_class is not WorkClass.ORG:
        return False
    return not (is_leaf and has_non_org_ancestor)
```

- [ ] **Step 5: Запустить — убедиться, что проходят**

Run: `cd backend; PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -v`
Expected: PASS (новые + существующие). Затем `cd backend; uv run ruff check app/domain/classification.py tests/test_classification.py` → clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/classification.py backend/tests/test_classification.py
git commit -m "feat(orgfilter): build_embedding_input выбрасывает свой org-токен + is_excluded"
```

---

### Task 2: Override в `_classify_nodes` (код-based лист + non-org предок + защитный инвариант)

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py`
- Test: `backend/tests/test_estimate_matching_service.py` (существует — добавить тесты)

**Interfaces:**
- Consumes: `is_excluded`, `build_embedding_input` (Task 1); `WorkClass` ([entities.py](../../../backend/app/domain/entities.py)); `NodeClassification`, `ClassifiableNode`.
- Produces: обновлённый `EstimateMatchingService._classify_nodes`; `EstimateMatchingService._parent_of(code) -> str | None`.

Текущий проход 2 (что заменяем) в [estimate_matching_service.py](../../../backend/app/services/estimate_matching_service.py): цикл строит `ancestors`, зовёт `build_embedding_input(n.name, ancestors)`, кладёт `NodeClassification(node_id=n.id, excluded=cls_by_id[n.id] is WorkClass.ORG, embedding_input=crumb)`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_estimate_matching_service.py` (импорты `EstimateNode`, `NewEstimate`, `NodeClassification`, `WorkClass`, `FakeEstimateRepository`, `FakeWorkTypeClassifier`, `EstimateMatchingService`, `MatchingService`, `FakeRepository`/`_ready_articles`, `FakeLLMMatcher`, `_Embedder` уже есть в файле — переиспользовать):

```python
def _seed_tree(repo: FakeEstimateRepository, tree: list[tuple[str, str, str | None]]):
    """tree: список (code, name, parent_code) в порядке сметы (source_index = индекс)."""
    nodes = [
        EstimateNode(code=c, name=nm, parent_code=p, section_type=None,
                     embedding_input=nm, source_index=i, depth=c.count(".") + 1)
        for i, (c, nm, p) in enumerate(tree)
    ]
    return repo.create(NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"), nodes)


def _classify_svc(repo, *, classifier):
    art = _ready_articles([])
    matcher = MatchingService(art, embedder=None, llm_matcher=FakeLLMMatcher())
    return EstimateMatchingService(matcher=matcher, embedder=_Embedder(),
                                   estimates=repo, articles=art, classifier=classifier)


def test_classify_rescues_org_leaf_under_work():
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [
        ("1", "Подготовительные работы", None),   # WORK (лексика)
        ("1.1", "Корпус 8", "1"),                  # ORG-лист под work → СПАСТИ
        ("2", "1 Этап ЖК", None),                  # ORG, нет work-предка → excluded
        ("2.1", "Монтаж кровли", "2"),             # WORK-ребёнок 2 (делает 2 не-листом)
    ])
    svc = _classify_svc(repo, classifier=FakeWorkTypeClassifier(default=WorkClass.WORK))
    svc._classify_nodes(est.id)
    by_code = {r.code: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert by_code["1.1"].status == "pending"                    # спасён (не excluded)
    assert by_code["1.1"].embedding_input == "Подготовительные работы"  # свой org-токен выброшен
    assert by_code["2"].status == "excluded"                     # не-лист org-разделитель
    assert by_code["1"].status == "pending" and by_code["2.1"].status == "pending"
    assert by_code["2.1"].embedding_input == "Монтаж кровли"      # ORG-предок «1 Этап ЖК» выброшен у WORK-узла


def test_classify_org_leaf_without_work_ancestor_excluded():
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [
        ("1", "1 Этап ЖК", None),     # ORG-корень (нет предков)
        ("1.1", "Корпус 8", "1"),     # ORG-лист, но единственный предок ORG → нет non-org → excluded
    ])
    svc = _classify_svc(repo, classifier=FakeWorkTypeClassifier(default=WorkClass.WORK))
    svc._classify_nodes(est.id)
    by_code = {r.code: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert by_code["1.1"].status == "excluded"


def test_classify_unsure_ancestor_counts_as_non_org():
    # регресс: предок UNSURE (НЕ WORK) — non-org, спасение org-листа под ним должно сработать.
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [
        ("1", "Смешанный узел ЖК", None),   # орг-токен ЖК + голова → UNSURE → классификатор
        ("1.1", "Корпус 8", "1"),           # ORG-лист под UNSURE-предком → СПАСТИ
    ])
    clf = FakeWorkTypeClassifier(verdicts={"Смешанный узел ЖК": WorkClass.UNSURE}, default=WorkClass.UNSURE)
    svc = _classify_svc(repo, classifier=clf)
    svc._classify_nodes(est.id)
    by_code = {r.code: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert by_code["1.1"].status == "pending"   # спасён через UNSURE-предка
    assert by_code["1.1"].embedding_input == "Смешанный узел ЖК"  # UNSURE-предок в крошке, свой org вне


def test_classify_invariant_kept_node_empty_crumb_raises(monkeypatch):
    # Защитный инвариант (точка A3): рассинхрон is_excluded↔build_embedding_input ловится.
    import app.services.estimate_matching_service as svc_mod
    repo = FakeEstimateRepository()
    est = _seed_tree(repo, [("1", "Подготовительные работы", None), ("1.1", "Корпус 8", "1")])
    # Индуцируем рассинхрон: крошка всегда пустая, при этом 1.1 спасается (kept) → инвариант бьёт.
    monkeypatch.setattr(svc_mod, "build_embedding_input", lambda *a, **k: "")
    svc = _classify_svc(repo, classifier=FakeWorkTypeClassifier(default=WorkClass.WORK))
    import pytest
    with pytest.raises(AssertionError):
        svc._classify_nodes(est.id)
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend; PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -v -k "rescue or without_work or unsure_ancestor or empty_crumb"`
Expected: FAIL — спасения нет (старый код исключает `1.1`), `_parent_of` отсутствует.

- [ ] **Step 3: Добавить импорт и `_parent_of`**

В `backend/app/services/estimate_matching_service.py` в импорт из `app.domain.classification` добавить `is_excluded` (рядом с `build_embedding_input`, `classify_lexical`). Затем рядом с `_ancestor_codes` добавить статический метод:

```python
    @staticmethod
    def _parent_of(code: str) -> str | None:
        segs = code.split(".")
        return ".".join(segs[:-1]) or None
```

- [ ] **Step 4: Переписать проход 2 в `_classify_nodes`**

**Контекст (НЕ меняем):** проход 1 уже строит `name_by_code`, `cls_by_id` (класс по id) и
`repr_id_by_code` (код→id первого вхождения, `setdefault`) — все три существуют, их не трогаем.
`logger` в модуле определён (`logging.getLogger(__name__)`, сервис уже логирует). Метод имеет сигнатуру
`-> int` и заканчивается этим проходом; `return sum(...)` (число excluded) — существующее поведение,
его читает вызывающий `match_estimate` для лог-строки «excluded=N». Заменить блок «Проход 2» на:

```python
        # Проход 2: override (код-based лист + non-org предок) + крошка с выбросом своего org → bulk.
        parent_codes = {p for n in nodes if (p := self._parent_of(n.code))}
        results: list[NodeClassification] = []
        for n in nodes:
            # ancestors — ПОЛНЫЙ (name, cls) по всем предкам, БЕЗ предварительной фильтрации ORG:
            # has_non_org_anc и build_embedding_input фильтруют ORG изнутри (эквивалентность инв.2).
            ancestors = [
                (name_by_code[a], cls_by_id[repr_id_by_code[a]])
                for a in self._ancestor_codes(n.code)
                if a in name_by_code
            ]
            own = cls_by_id[n.id]
            is_leaf = n.code not in parent_codes
            has_non_org_anc = any(cls is not WorkClass.ORG for _, cls in ancestors)
            excluded = is_excluded(own, is_leaf=is_leaf, has_non_org_ancestor=has_non_org_anc)
            crumb = build_embedding_input(n.name, ancestors, self_class=own)
            # Инвариант 2: kept-узел ОБЯЗАН иметь непустую крошку. Не ловит логику _classify_nodes
            # (она такого не породит), а ловит будущий рассинхрон is_excluded↔build_embedding_input.
            if not excluded and not crumb:
                logger.error(
                    "kept-узел с пустой крошкой: id=%s code=%s class=%s", n.id, n.code, own
                )
                raise AssertionError(f"kept node with empty crumb: {n.id} {n.code} {own}")
            results.append(
                NodeClassification(node_id=n.id, excluded=excluded, embedding_input=crumb)
            )
        self._estimates.save_node_classifications(results)  # один commit, охрана статуса
        return sum(1 for r in results if r.excluded)
```

- [ ] **Step 5: Запустить — убедиться, что проходят**

Run: `cd backend; PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -v`
Expected: PASS (новые + существующие). Затем полный сует: `cd backend; PYTHONIOENCODING=utf-8 uv run pytest -q` — без регрессий. Линт: `cd backend; uv run ruff check app/services/estimate_matching_service.py tests/test_estimate_matching_service.py` → clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/estimate_matching_service.py backend/tests/test_estimate_matching_service.py
git commit -m "feat(orgfilter): override — спасать org-лист с non-org предком (код-based лист)"
```

---

### Task 3: Замер на бенчмарке + закрытие 🔴 TECH_DEBT

**Files:**
- Modify: `docs/TECH_DEBT.md`

**Предусловия (живой шаг — гоняет контроллер):** проэмбеженный справочник, валидный `backend/.env`, бенчмарк id=1 в БД (засеян ранее). Один прогон = платные API (~эмбеддинги + арбитр).

- [ ] **Step 1: Ре-прогон харнесса (живой, контроллер)**

Run: `just eval-matching`
Expected (матрица Группы A, проверена симуляцией в спеке):
```
ПОСЛЕ: TN=24  FP=1  FN=2   TP=781
```
- FN 30→2 (спасены 28); FP 0→1 (`5.2 «2 Этап БЦ»` — допущение D1); TP 753→781.
- В CSV-детализации убедиться: `5.2` теперь `kept`/structural (виден как FP — это датчик D1); 28 спасённых листьев — `kept` с work-крошкой.
- **Baseline датчика D1: FP=1** (= один бездетный этап-разделитель `5.2`). На втором объекте сравнивать с этим числом: FP должен ≈ числу бездетных org-листьев с work-предком.
- Если FN не упал до 2 или FP заметно >1 (≫ числа бездетных org-листьев с work-предком) — СТОП, разобрать (рассинхрон разметки Issue 1 либо провал D1 шире), не списывать на шум.

- [ ] **Step 2: Записать число уникальных статей среди спасённых**

Из CSV (или быстрым `python -c` по rows): среди спасённых (`kept`, бывших excluded) посчитать уникальные `gold_code`. Ожидаемо ~8 на 28 узлов (навесы-кластеры). Записать обе цифры в отчёт замера/девлог — «+28 TP» = 28 строк / 8 статей.

- [ ] **Step 3: Закрыть 🔴-пункт в TECH_DEBT**

В `docs/TECH_DEBT.md` перевести 🔴-пункт «Фильтр оргзаголовков: каркас-ЛИСТ под работным предком…» в «Погашено» (с датой), указав: фикс в `feat/orgfilter-leaf-rescue` (правило ORG+лист+non-org-предок), измеренный результат FN 30→2, остаток 2 (доказанно дёшев), принятый FP=1 на `5.2` (допущение D1, датчик = FP Группы A).

- [ ] **Step 4: Commit**

```bash
git add docs/TECH_DEBT.md
git commit -m "docs(tech-debt): закрыть 🔴 орг-фильтр (лист под work) — измерено харнессом"
```

---

## Замечания по интеграции

- **`classify_lexical` и LLM-классификатор не трогаем** — override чисто структурный, поверх любого ORG-вердикта.
- **Каскада нет:** override меняет только листья (у листа нет код-потомков) → `has_non_org_anc` по базовой классификации корректен в один проход (проверено на данных).
- **Листовость код-based**, не позиционная: смета — не строгий DFS-преордер (на бенчмарке 16 расхождений листовостей, см. спеку §Листовость); код-based консистентна с код-сегментной иерархией пайплайна и корректна на всех ORG-узлах.
- **Замер — один объект:** валидация, что правило делает задуманное, НЕ что обобщается. Допущения D1 (этап-с-детьми) и зависимость FP/FN от вердикта классификатора (лексич. `5.2` стабилен, LLM-узлы плавают) — первые кандидаты на провал на втором объекте; датчик — FP Группы A.
