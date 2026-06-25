# Фильтрация организационных заголовков (lean v1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** До эмбеддинга классифицировать узлы сметы в WORK/ORG/UNSURE по смыслу имени, обратимо исключить чистые орг-заголовки из эмбеддинга/матчинга (статусом `excluded`) и вырезать ORG-предков из крошки `embedding_input`.

**Architecture:** Чистый каскад «лексика → LLM» в доменном слое + дешёвый LLM-классификатор за портом в infrastructure. Оркестрация — новый шаг в `EstimateMatchingService` до эмбеддинга. Класс `WorkClass` считается **в памяти** (для выреза ORG-предков); в БД персистится только `status='excluded'` у орг-заголовков — отдельной колонки нет.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy + pgvector, Anthropic SDK (Haiku-класс), pytest.

**Спека:** [docs/superpowers/specs/2026-06-25-estimate-org-header-filter-design.md](../specs/2026-06-25-estimate-org-header-filter-design.md)

## Global Constraints

- ruff line-length 100, `target py311`; каждый модуль начинается с `from __future__ import annotations`; type hints обязательны.
- Доменный слой (`app/domain/`) — без импортов FastAPI/SQLAlchemy/SDK.
- Все команды через `uv run` из `backend/`. Системный `python`/`pip` не вызывать.
- Кириллица в stdout: префикс `PYTHONIOENCODING=utf-8` при запуске pytest, иначе `UnicodeEncodeError`.
- Юнит-тесты НЕ ходят в реальную БД/AI — фейки портов (`tests/fakes.py`) + `app.dependency_overrides`.
- Бэкенд на порту 8260. Без Docker. Секреты только в `backend/.env`.
- Коммиты — conventional; в конце сообщения `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Асимметрия ошибок (инвариант дизайна): при любом сомнении класс — НЕ `ORG` (ложный ORG = молчаливый пропуск работы).
- **Без миграции:** колонка `status` уже `VARCHAR(32)` без CHECK — значение `'excluded'` новой схемы не требует. Колонку `node_class` НЕ заводим.

## File Structure

| Файл | Ответственность | Действие |
|---|---|---|
| `backend/app/domain/classification.py` | Лексика: оргтокены, `has_work_word`, `classify_lexical`, `build_embedding_input` | Create |
| `backend/app/domain/entities.py` | `WorkClass`, `NodeToClassify`, `ClassifiableNode`, `EstimateRowStatus.EXCLUDED` | Modify |
| `backend/app/domain/ports.py` | Порт `WorkTypeClassifier`; методы `fetch_all_nodes`/`save_node_classifications` | Modify |
| `backend/app/infrastructure/ai/anthropic_classifier.py` | LLM-адаптер классификатора + промпт/парсинг | Create |
| `backend/app/core/config.py` | `classifier_model`, `classifier_batch_size` | Modify |
| `backend/app/infrastructure/db/estimate_repository.py` | persistence `excluded` + крошка; исключение из выборок/счётчиков | Modify |
| `backend/app/services/estimate_matching_service.py` | шаг классификации + пересборка крошки | Modify |
| `backend/app/api/deps.py` | DI классификатора | Modify |
| `backend/tests/fakes.py` | `FakeWorkTypeClassifier` + зеркало изменений репозитория | Modify |
| `backend/tests/test_classification.py` | юнит-тесты домена | Create |
| `backend/tests/test_anthropic_classifier.py` | юнит-тесты адаптера | Create |
| `backend/tests/test_estimate_matching_service.py` | тесты оркестрации/репозитория | Modify |
| `backend/tests/test_estimate_export_service.py` | характеризующий тест экспорта | Modify/Create |

> **Без API-задачи:** новое поле в `EstimateRowOut` не нужно — фронт отличает орг-заголовки по `status='excluded'`. `node_class`-колонки и миграции тоже нет.

---

### Task 1: Оргтокены (домен, чистая логика)

**Files:**
- Create: `backend/app/domain/classification.py`
- Test: `backend/tests/test_classification.py`

**Interfaces:**
- Produces: `contains_org_token(name: str) -> bool` — есть ли в имени оргтокен (морфология + литералы ЖК/БЦ); `_is_org_token(token: str) -> bool` — является ли отдельный токен оргтокеном.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_classification.py
from __future__ import annotations

import pytest

from app.domain.classification import contains_org_token


@pytest.mark.parametrize(
    "name",
    [
        "I и 2 Этапы БЦ и ЖК",   # founding-пример: «Этапы» (мн.ч.) + литералы
        "Корпусов 5",
        "Очереди строительства",
        "1 Этап ЖК",
        "Корпус № 2; 3; 4",
    ],
)
def test_contains_org_token_true(name: str) -> None:
    assert contains_org_token(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Устройство кровли",
        "работы на этаже 3",   # этаж ≠ этап
        "Этажность здания",    # этаж + здание (не оргтокены)
        "Гидроизоляция подземной части здания",
    ],
)
def test_contains_org_token_false(name: str) -> None:
    assert contains_org_token(name) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -v`
Expected: FAIL — `ModuleNotFoundError: app.domain.classification`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domain/classification.py
"""Лексическая классификация узлов сметы (WORK/ORG/UNSURE). Чистый домен, без I/O."""

from __future__ import annotations

import re

# Оргтокены — маленькое закрытое множество. Стемы заякорены на начало слова и
# матчат русские окончания (этап→этапы/этапов); «этап» НЕ ловит «этаж».
# ВАЖНО: «пусков» матчит «пусковой», но не «пусконаладочные» (это работа).
_ORG_STEMS = (
    "этап", "очеред", "пусков", "корпус", "литер", "секци", "объект",
)
# «блок-секция» ловится через «секци» (search по имени), отдельный стем не нужен;
# «блок» в стемы НЕ добавляем — это и работный термин («блок ФБС»). «блок-секция N»
# уйдёт в LLM как смесь (голова «блок») — безопасно по асимметрии.
# Литералы без окончаний — организационные аббревиатуры.
_ORG_LITERALS = ("жк", "бц")

_ORG_STEM_RE = re.compile(
    r"(?<![а-яё])(?:" + "|".join(_ORG_STEMS) + r")[а-яё]*",
    re.IGNORECASE,
)
_ORG_LITERAL_RE = re.compile(
    r"(?<![а-яёa-z])(?:" + "|".join(_ORG_LITERALS) + r")(?![а-яёa-z])",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яёЁ]+")


def _is_org_token(token: str) -> bool:
    low = token.lower()
    if low in _ORG_LITERALS:
        return True
    return _ORG_STEM_RE.fullmatch(low) is not None


def contains_org_token(name: str) -> bool:
    return (
        _ORG_STEM_RE.search(name) is not None
        or _ORG_LITERAL_RE.search(name) is not None
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -v`
Expected: PASS (9 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/classification.py backend/tests/test_classification.py
git commit -m "$(printf 'feat(classify): матчинг оргтокенов сметы (морфология + литералы ЖК/БЦ)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: `has_work_word` (домен, чистая логика)

**Files:**
- Modify: `backend/app/domain/classification.py`
- Test: `backend/tests/test_classification.py`

**Interfaces:**
- Consumes: `_is_org_token` (Task 1).
- Produces: `has_work_word(name: str) -> bool` — есть ли в имени работная голова (определено НЕГАТИВНО). Аббревиатуры 2–4 заглавные = голова. Оргтокены (вкл. литералы ЖК/БЦ) отсекаются ДО аббревиатурного правила.

- [ ] **Step 1: Write the failing test**

```python
# добавить в backend/tests/test_classification.py
from app.domain.classification import has_work_word


@pytest.mark.parametrize("name", ["МАФ", "ЗИП", "VRF", "КС", "Устройство кровли"])
def test_has_work_word_true(name: str) -> None:
    assert has_work_word(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "1 Этап ЖК",        # ЖК — литерал-оргтокен, не голова (до аббрев-правила!)
        "2 Этап БЦ",
        "Корпус № 2; 3; 4",
        "и в том числе",    # стоп-слова
        "прочее",
    ],
)
def test_has_work_word_false(name: str) -> None:
    assert has_work_word(name) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k has_work_word -v`
Expected: FAIL — `ImportError: cannot import name 'has_work_word'`.

- [ ] **Step 3: Write minimal implementation**

```python
# добавить в backend/app/domain/classification.py (после _is_org_token)

# Единственный вручную поддерживаемый словарь, кроме оргтокенов.
# NB: «работы»/«работ» НЕ в стоп-листе — это слабый РАБОТНЫЙ сигнал; их стоп-листинг
# опрокинул бы «работы корпуса 5» в молчаливый ORG (нарушение асимметрии).
_STOPWORDS = frozenset(
    {
        "прочее", "прочие", "и", "в", "с", "по", "на",
        "для", "том", "числе", "включая", "т.п", "тп", "т.ч", "тч",
    }
)


def _is_abbrev(token: str) -> bool:
    return 2 <= len(token) <= 4 and token.isupper()


def has_work_word(name: str) -> bool:
    """True, если есть содержательный (не орг, не стоп) токен.

    Ошибается В СТОРОНУ «голова есть»: аббревиатура 2–4 заглавные считается головой.
    Оргтокены (вкл. ЖК/БЦ) отсекаются ПЕРВЫМИ — иначе они сами 2 заглавные и
    ложно сочлись бы головой.
    """
    for token in _TOKEN_RE.findall(name):
        if _is_org_token(token):
            continue
        if token.lower() in _STOPWORDS:
            continue
        if len(token) >= 3 or _is_abbrev(token):
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k has_work_word -v`
Expected: PASS (10 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/classification.py backend/tests/test_classification.py
git commit -m "$(printf 'feat(classify): has_work_word — негативное определение работной головы\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: `WorkClass` + `classify_lexical`

**Files:**
- Modify: `backend/app/domain/entities.py`
- Modify: `backend/app/domain/classification.py`
- Test: `backend/tests/test_classification.py`

**Interfaces:**
- Consumes: `contains_org_token`, `has_work_word`.
- Produces: `WorkClass(StrEnum)` = `WORK/ORG/UNSURE`; `classify_lexical(name: str) -> WorkClass`.

- [ ] **Step 1: Write the failing test**

```python
# добавить в backend/tests/test_classification.py
from app.domain.classification import classify_lexical
from app.domain.entities import WorkClass


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Корпус № 2; 3; 4", WorkClass.ORG),          # чистый каркас → ORG без LLM
        ("1 Этап ЖК", WorkClass.ORG),                  # пересечение ЖК-литерал × аббрев
        ("Устройство кровли", WorkClass.WORK),         # нет оргтокена → WORK
        ("Наружное освещение 1 Этап ЖК", WorkClass.UNSURE),  # смесь → LLM
        ("МАФ Корпус 3", WorkClass.UNSURE),            # аббрев-работа + орг → НЕ ORG
        ("Объект озеленения", WorkClass.UNSURE),       # объект + голова → НЕ молчаливый ORG
    ],
)
def test_classify_lexical(name: str, expected: WorkClass) -> None:
    assert classify_lexical(name) is expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k classify_lexical -v`
Expected: FAIL — `ImportError: cannot import name 'WorkClass'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domain/entities.py — добавить рядом с прочими StrEnum
class WorkClass(StrEnum):
    """Класс узла сметы по смыслу имени (для фильтрации оргзаголовков). В БД НЕ хранится."""

    WORK = "work"      # вид работ — матчится
    ORG = "org"        # организационный заголовок — исключается (status='excluded')
    UNSURE = "unsure"  # неоднозначно — трактуем как WORK (асимметрия ошибок)
```

```python
# backend/app/domain/classification.py — добавить импорт в шапку и функцию
from app.domain.entities import WorkClass


def classify_lexical(name: str) -> WorkClass:
    """Каскад: нет оргтокена → WORK; орг + нет головы → ORG; орг + голова → UNSURE."""
    if not contains_org_token(name):
        return WorkClass.WORK
    if has_work_word(name):
        return WorkClass.UNSURE
    return WorkClass.ORG
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k classify_lexical -v`
Expected: PASS (6 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/classification.py backend/tests/test_classification.py
git commit -m "$(printf 'feat(classify): WorkClass + classify_lexical (каскад лексики)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: `build_embedding_input` (выброс ORG-предков)

**Files:**
- Modify: `backend/app/domain/classification.py`
- Test: `backend/tests/test_classification.py`

**Interfaces:**
- Consumes: `WorkClass`.
- Produces: `build_embedding_input(self_name: str, ancestors: list[tuple[str, WorkClass]], *, separator: str = ". ", collapse_repeats: bool = True) -> str` — крошка root→узел с выброшенными ORG-предками, схлопыванием подряд идущих повторов и нормализацией пробелов.

- [ ] **Step 1: Write the failing test**

```python
# добавить в backend/tests/test_classification.py
from app.domain.classification import build_embedding_input


def test_build_embedding_input_drops_org_ancestors() -> None:
    ancestors = [
        ("1 Этап ЖК", WorkClass.ORG),
        ("Фасадные работы", WorkClass.WORK),
    ]
    assert build_embedding_input("Устройство навесных фасадов", ancestors) == (
        "Фасадные работы. Устройство навесных фасадов"
    )


def test_build_embedding_input_normalizes_and_collapses() -> None:
    ancestors = [("Устройство  заполнения", WorkClass.WORK)]  # двойной пробел
    assert build_embedding_input("Устройство  заполнения", ancestors) == (
        "Устройство заполнения"  # повтор схлопнут, пробелы нормализованы
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k build_embedding_input -v`
Expected: FAIL — `ImportError: cannot import name 'build_embedding_input'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domain/classification.py — добавить
def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _collapse_consecutive(parts: list[str]) -> list[str]:
    out: list[str] = []
    for part in parts:
        if not out or out[-1] != part:
            out.append(part)
    return out


def build_embedding_input(
    self_name: str,
    ancestors: list[tuple[str, WorkClass]],
    *,
    separator: str = ". ",
    collapse_repeats: bool = True,
) -> str:
    """Крошка root→узел; ORG-предки выброшены (справочник org-free, не загрязняем вектор)."""
    parts = [_normalize_ws(name) for name, cls in ancestors if cls is not WorkClass.ORG]
    parts.append(_normalize_ws(self_name))
    if collapse_repeats:
        parts = _collapse_consecutive(parts)
    return separator.join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k build_embedding_input -v`
Expected: PASS (2 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/classification.py backend/tests/test_classification.py
git commit -m "$(printf 'feat(classify): build_embedding_input с выбросом ORG-предков\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 5: Порт `WorkTypeClassifier` + `NodeToClassify` + фейк

**Files:**
- Modify: `backend/app/domain/entities.py`
- Modify: `backend/app/domain/ports.py`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/test_classification.py`

**Interfaces:**
- Produces: `NodeToClassify(name: str, ancestors: tuple[str, ...])`; порт `WorkTypeClassifier.classify(items: list[NodeToClassify]) -> list[WorkClass]` (возврат выровнен по `items`); `FakeWorkTypeClassifier(verdicts: dict[str, WorkClass] | None, default: WorkClass = WorkClass.UNSURE)`.

- [ ] **Step 1: Write the failing test**

```python
# добавить в backend/tests/test_classification.py
from app.domain.entities import NodeToClassify
from tests.fakes import FakeWorkTypeClassifier


def test_fake_classifier_aligns_output_to_input() -> None:
    clf = FakeWorkTypeClassifier(verdicts={"Гостиница Заря": WorkClass.ORG})
    items = [
        NodeToClassify(name="Гостиница Заря", ancestors=("Фасадные работы",)),
        NodeToClassify(name="что-то ещё", ancestors=()),
    ]
    assert clf.classify(items) == [WorkClass.ORG, WorkClass.UNSURE]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k fake_classifier -v`
Expected: FAIL — `ImportError: cannot import name 'NodeToClassify'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domain/entities.py — добавить (после MatchableNode)
@dataclass(frozen=True, slots=True)
class NodeToClassify:
    """Узел на вход LLM-классификатору: имя + цепочка предков (root→parent) как контекст."""

    name: str
    ancestors: tuple[str, ...]
```

```python
# backend/app/domain/ports.py — добавить импорт NodeToClassify, WorkClass и класс
class WorkTypeClassifier(ABC):
    """Порт классификатора вид-работ/оргструктура (дешёвая LLM, отдельно от арбитра)."""

    @abstractmethod
    def classify(self, items: list[NodeToClassify]) -> list[WorkClass]:
        """Возврат выровнен по items. При сбое/неоднозначности → WorkClass.UNSURE."""
        ...
```

```python
# backend/tests/fakes.py — добавить импорты (NodeToClassify, WorkClass, WorkTypeClassifier) и класс
class FakeWorkTypeClassifier(WorkTypeClassifier):
    def __init__(
        self,
        verdicts: dict[str, WorkClass] | None = None,
        default: WorkClass = WorkClass.UNSURE,
    ) -> None:
        self._verdicts = verdicts or {}
        self._default = default
        self.calls: list[list[NodeToClassify]] = []

    def classify(self, items: list[NodeToClassify]) -> list[WorkClass]:
        self.calls.append(items)
        return [self._verdicts.get(i.name, self._default) for i in items]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k fake_classifier -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/ports.py backend/tests/fakes.py backend/tests/test_classification.py
git commit -m "$(printf 'feat(classify): порт WorkTypeClassifier + NodeToClassify + фейк\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 6: LLM-адаптер классификатора (Anthropic) + конфиг

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/infrastructure/ai/anthropic_classifier.py`
- Test: `backend/tests/test_anthropic_classifier.py`

**Interfaces:**
- Consumes: порт `WorkTypeClassifier`, `NodeToClassify`, `WorkClass`.
- Produces: `AnthropicWorkClassifier(api_key, model, batch_size, ...)` реализует `classify`; чистые `build_batch_prompt(items) -> str` и `parse_classifications(text, n) -> list[WorkClass]`. Фолбэк: любой сбой/битый JSON/несовпадение длины → весь батч `UNSURE`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_anthropic_classifier.py
from __future__ import annotations

from app.domain.entities import NodeToClassify, WorkClass
from app.infrastructure.ai.anthropic_classifier import (
    AnthropicWorkClassifier,
    parse_classifications,
)


class _StubMessages:
    def __init__(self, text: str) -> None:
        self._text = text

    def create(self, **_kw):  # noqa: ANN003
        class _Block:
            text = self._text

        class _Resp:
            content = [_Block()]

        return _Resp()


class _StubClient:
    def __init__(self, text: str) -> None:
        self.messages = _StubMessages(text)


def test_parse_classifications_maps_classes() -> None:
    text = '[{"i": 0, "class": "org"}, {"i": 1, "class": "work"}]'
    assert parse_classifications(text, 2) == [WorkClass.ORG, WorkClass.WORK]


def test_parse_unknown_class_becomes_unsure() -> None:
    text = '[{"i": 0, "class": "banana"}]'
    assert parse_classifications(text, 1) == [WorkClass.UNSURE]


def test_parse_strips_markdown_fences() -> None:
    text = '```json\n[{"i": 0, "class": "org"}]\n```'
    assert parse_classifications(text, 1) == [WorkClass.ORG]


def test_classify_returns_aligned_verdicts() -> None:
    client = _StubClient('[{"i": 0, "class": "org"}, {"i": 1, "class": "work"}]')
    clf = AnthropicWorkClassifier(api_key="x", client=client)
    items = [
        NodeToClassify("1 Этап ЖК", ()),
        NodeToClassify("Наружное освещение", ("1 Этап ЖК",)),
    ]
    assert clf.classify(items) == [WorkClass.ORG, WorkClass.WORK]


def test_broken_json_falls_back_to_unsure() -> None:
    client = _StubClient("не json вовсе")
    clf = AnthropicWorkClassifier(api_key="x", client=client)
    items = [NodeToClassify("a", ()), NodeToClassify("b", ())]
    assert clf.classify(items) == [WorkClass.UNSURE, WorkClass.UNSURE]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_anthropic_classifier.py -v`
Expected: FAIL — `ModuleNotFoundError: app.infrastructure.ai.anthropic_classifier`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/config.py — добавить поля в Settings (рядом с anthropic_llm_model)
    # Классификатор вид-работ/оргструктура — дешёвая модель, отдельно от арбитра матчинга.
    classifier_model: str = "claude-haiku-4-5"
    classifier_batch_size: int = 40
```

```python
# backend/app/infrastructure/ai/anthropic_classifier.py
"""WorkTypeClassifier через Anthropic SDK (дешёвая модель). Батч + фолбэк в UNSURE."""

from __future__ import annotations

import json

import anthropic
import httpx

from app.domain.entities import NodeToClassify, WorkClass
from app.domain.ports import WorkTypeClassifier
from app.infrastructure.retry import retry_transient

SYSTEM_PROMPT = (
    "Ты классифицируешь строки строительной сметы. Для каждого имени реши, "
    "является ли оно ОБОЗНАЧЕНИЕМ ВИДА СТРОИТЕЛЬНЫХ РАБОТ — где угодно в строке, "
    "независимо от порядка слов.\n"
    "- Если имя — ТОЛЬКО метка этапа/очереди/корпуса/объекта (организационный "
    "каркас) → класс \"org\".\n"
    "- Если имя называет работу, пусть даже привязанную к этапу/корпусу → \"work\".\n"
    "- Если по имени и предкам уверенно решить нельзя → \"unsure\".\n"
    "При сомнении выбирай \"work\" или \"unsure\", НЕ \"org\".\n"
    "Ответ — СТРОГО JSON-массив объектов {\"i\": <индекс>, \"class\": "
    "\"work|org|unsure\"} без преамбулы и markdown."
)

_CLASS_BY_NAME = {"work": WorkClass.WORK, "org": WorkClass.ORG, "unsure": WorkClass.UNSURE}


def build_batch_prompt(items: list[NodeToClassify]) -> str:
    lines = []
    for i, item in enumerate(items):
        ctx = " / ".join(item.ancestors) if item.ancestors else "(корень)"
        lines.append(f"{i}. имя: {item.name!r} | предки: {ctx}")
    return "Классифицируй:\n" + "\n".join(lines)


def _strip_fences(text: str) -> str:
    """Снять markdown-ограждение ```json … ``` — модель иногда оборачивает вопреки промпту."""
    s = text.strip()
    if not s.startswith("```"):
        return s
    s = s[3:]
    if s[:4].lower() == "json":
        s = s[4:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def parse_classifications(text: str, n: int) -> list[WorkClass]:
    """Строгий парс. Любая аномалия (битый JSON, не та длина) → всё UNSURE."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return [WorkClass.UNSURE] * n
    if not isinstance(data, list) or len(data) != n:
        return [WorkClass.UNSURE] * n
    out: list[WorkClass] = [WorkClass.UNSURE] * n
    for entry in data:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("i")
        if isinstance(idx, int) and 0 <= idx < n:
            out[idx] = _CLASS_BY_NAME.get(str(entry.get("class")).lower(), WorkClass.UNSURE)
    return out


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, anthropic.APIConnectionError)


class AnthropicWorkClassifier(WorkTypeClassifier):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5",
        batch_size: int = 40,
        timeout_s: float = 30.0,
        retry_budget: int = 3,
        *,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self._client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
        self._model = model
        self._batch_size = batch_size
        self._retry_budget = retry_budget

    def classify(self, items: list[NodeToClassify]) -> list[WorkClass]:
        out: list[WorkClass] = []
        for start in range(0, len(items), self._batch_size):
            chunk = items[start : start + self._batch_size]
            out.extend(self._classify_chunk(chunk))
        return out

    def _classify_chunk(self, chunk: list[NodeToClassify]) -> list[WorkClass]:
        prompt = build_batch_prompt(chunk)

        def _call() -> str:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text if resp.content else ""

        try:
            text = retry_transient(_call, budget=self._retry_budget, classify=_is_transient)
        except Exception:  # noqa: BLE001 — фолбэк по асимметрии: сбой → UNSURE, не ORG
            return [WorkClass.UNSURE] * len(chunk)
        return parse_classifications(text, len(chunk))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_anthropic_classifier.py -v`
Expected: PASS (5 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/infrastructure/ai/anthropic_classifier.py backend/tests/test_anthropic_classifier.py
git commit -m "$(printf 'feat(classify): Anthropic LLM-классификатор (батч, строгий JSON, фолбэк UNSURE)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 7: Репозиторий — persistence `excluded` + чистка крошки + исключение из выборок

**Files:**
- Modify: `backend/app/domain/entities.py` (`EstimateRowStatus.EXCLUDED`, `ClassifiableNode`)
- Modify: `backend/app/domain/ports.py` (методы `EstimateRepository`)
- Modify: `backend/app/infrastructure/db/estimate_repository.py`
- Modify: `backend/tests/fakes.py` (зеркало в `FakeEstimateRepository`)
- Test: `backend/tests/test_estimate_matching_service.py`

**Interfaces:**
- Produces:
  - `EstimateRowStatus.EXCLUDED = "excluded"`.
  - `ClassifiableNode(id: int, code: str, name: str)`.
  - `NodeClassification(node_id: int, excluded: bool, embedding_input: str)` — результат прохода для одной строки.
  - `EstimateRepository.fetch_all_nodes(estimate_id) -> list[ClassifiableNode]` (все узлы по возрастанию `source_index`).
  - `EstimateRepository.save_node_classifications(results: list[NodeClassification]) -> None` — **bulk, один commit**. Охранный переход: пишет только строки в `status IN ('pending','excluded')` (терминальные матч-статусы и ревью НЕ трогает); `excluded=True → 'excluded'`, `excluded=False → 'pending'` (возврат из корзины на повторном прогоне). Идемпотентно и безопасно к повторному запуску `match_estimate`.
  - `fetch_unembedded_nodes` дополнительно фильтрует `status != 'excluded'`; `nodes_count` в `list_for_owner` считает `status != 'excluded'`.
  - (`fetch_matchable_nodes`/`count_unfinished_nodes`/`count_node_errors` менять НЕ нужно — `excluded` не входит в их наборы статусов; проверено в коде.)

**Почему bulk + охрана статуса:**
- **Один commit** вместо ~809 (латентность round-trip на строку + атомарность: падение на середине не оставит половину строк переклассифицированными).
- **Охрана `status IN ('pending','excluded')`**: `_classify_nodes` зовётся каждым `match_estimate` (в т.ч. на gate-ретрае и ручном ре-триггере). Без охраны (а) безусловный `'excluded'` затёр бы уже проставленный матч-статус, (б) узел, который LLM в прошлый прогон счёл ORG, а в этот — WORK, залип бы в `excluded` навсегда. Переход только `pending↔excluded` оба риска снимает.

- [ ] **Step 1: Write the failing test (через фейк)**

```python
# добавить в backend/tests/test_estimate_matching_service.py
from app.domain.entities import EstimateNode, NewEstimate, NodeClassification
from tests.fakes import FakeEstimateRepository


def _seed_one(repo: FakeEstimateRepository, name: str) -> int:
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [EstimateNode(code="1", name=name, parent_code=None, section_type=None,
                      embedding_input=name, source_index=0, depth=1)],
    )
    return est.rows[0].id


def test_fake_repo_excludes_marked_org() -> None:
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "1 Этап ЖК")
    repo.save_node_classifications([NodeClassification(nid, excluded=True, embedding_input="1 Этап ЖК")])
    assert repo.fetch_unembedded_nodes(1, after_id=0, limit=10) == []
    assert repo.count_unfinished_nodes(1) == 0
    assert repo.list_for_owner(1, is_admin=True)[0].nodes_count == 0


def test_fake_repo_survivor_keeps_pending_and_new_breadcrumb() -> None:
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.save_node_classifications([NodeClassification(nid, excluded=False, embedding_input="Чистая крошка")])
    pend = repo.fetch_unembedded_nodes(1, after_id=0, limit=10)
    assert pend[0].embedding_input == "Чистая крошка"
    assert repo.count_unfinished_nodes(1) == 1


def test_fake_repo_classification_never_clobbers_matched_status() -> None:
    # охрана: переклассификация на повторном прогоне не трогает терминальный матч-статус
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "Устройство кровли")
    repo.nodes[nid]["status"] = "confident"  # как будто уже сматчено
    repo.save_node_classifications([NodeClassification(nid, excluded=True, embedding_input="x")])
    assert repo.get(1, 1, is_admin=True).rows[0].status == "confident"


def test_fake_repo_excluded_flips_back_to_pending() -> None:
    # узел, ошибочно исключённый в прошлый прогон, на этом возвращается в матчинг
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.save_node_classifications([NodeClassification(nid, excluded=True, embedding_input="x")])
    repo.save_node_classifications([NodeClassification(nid, excluded=False, embedding_input="x")])
    assert repo.count_unfinished_nodes(1) == 1  # снова pending
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -k fake_repo -v`
Expected: FAIL — `ImportError: cannot import name 'NodeClassification'`.

- [ ] **Step 3a: Сущности + порт**

```python
# backend/app/domain/entities.py — в EstimateRowStatus добавить:
    EXCLUDED = "excluded"  # чистый орг-заголовок: исключён из матчинга (обратимо)
```

```python
# backend/app/domain/entities.py — добавить (после MatchableNode)
@dataclass(frozen=True, slots=True)
class ClassifiableNode:
    """Узел для прохода классификации: id + код (для дерева) + имя."""

    id: int
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class NodeClassification:
    """Результат классификации одной строки (для bulk-записи)."""

    node_id: int
    excluded: bool
    embedding_input: str
```

```python
# backend/app/domain/ports.py — добавить в EstimateRepository (импортнуть ClassifiableNode, NodeClassification)
    @abstractmethod
    def fetch_all_nodes(self, estimate_id: int) -> list[ClassifiableNode]:
        """Все узлы сметы (id, code, name) по возрастанию source_index."""
        ...

    @abstractmethod
    def save_node_classifications(self, results: list[NodeClassification]) -> None:
        """Bulk, один commit. Охрана: пишет только строки в status IN ('pending','excluded');
        excluded=True→'excluded', False→'pending'. Терминальные матч-статусы/ревью не трогает."""
        ...
```

- [ ] **Step 3b: Реализация в SqlAlchemy-репозитории**

```python
# backend/app/infrastructure/db/estimate_repository.py
# импортировать ClassifiableNode, NodeClassification, EstimateRowStatus из app.domain.entities.

    def fetch_all_nodes(self, estimate_id: int) -> list[ClassifiableNode]:
        stmt = (
            select(EstimateRowModel.id, EstimateRowModel.code, EstimateRowModel.name)
            .where(EstimateRowModel.estimate_id == estimate_id)
            .order_by(EstimateRowModel.source_index)
        )
        return [
            ClassifiableNode(id=r.id, code=r.code, name=r.name)
            for r in self._session.execute(stmt)
        ]

    def save_node_classifications(self, results: list[NodeClassification]) -> None:
        # Охрана: только pending↔excluded. Терминальные матч-статусы и ревью неприкосновенны.
        for r in results:
            target = EstimateRowStatus.EXCLUDED if r.excluded else EstimateRowStatus.PENDING
            self._session.execute(
                update(EstimateRowModel)
                .where(
                    EstimateRowModel.id == r.node_id,
                    EstimateRowModel.status.in_(("pending", "excluded")),
                )
                .values(status=str(target), embedding_input=r.embedding_input)
            )
        self._session.commit()  # один commit на весь проход (атомарность + латентность)

# в fetch_unembedded_nodes — добавить в .where(...):
#         EstimateRowModel.status != "excluded",

# в list_for_owner — counts subquery считает только не-excluded:
#         .where(EstimateRowModel.status != "excluded")   перед .group_by(...)
```

- [ ] **Step 3c: Зеркало в фейке**

```python
# backend/tests/fakes.py — FakeEstimateRepository

    def fetch_all_nodes(self, estimate_id: int):  # noqa: ANN201
        from app.domain.entities import ClassifiableNode

        base = {r.id: r for e in self.estimates.values() for r in e.rows}
        rows = sorted(
            (n for n in self.nodes.values() if n["estimate_id"] == estimate_id),
            key=lambda n: n["id"],
        )
        return [
            ClassifiableNode(id=n["id"], code=base[n["id"]].code, name=base[n["id"]].name)
            for n in rows
        ]

    def save_node_classifications(self, results) -> None:  # noqa: ANN001
        for r in results:
            n = self.nodes[r.node_id]
            if n["status"] not in ("pending", "excluded"):
                continue  # охрана: матч-статус неприкосновенен
            n["status"] = "excluded" if r.excluded else "pending"
            n["embedding_input"] = r.embedding_input

# в fetch_unembedded_nodes — добавить условие n["status"] != "excluded"
# в list_for_owner — nodes_count = sum(
#     1 for r in e.rows if self.nodes[r.id]["status"] != "excluded"
# )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -k fake_repo -v`
Expected: PASS (4 cases).

> **Note (реальный репозиторий):** `SqlAlchemyEstimateRepository` юнит-тестами не покрыт (нет БД в юнитах). Изменения (3b) зеркалят логику фейка; верификация — ручной прогон сметы (раздел «Финальная проверка»). Миграция НЕ нужна (`excluded` — новое значение существующей `VARCHAR`-колонки `status`). Листовые позиции (`№`=NaN) в `estimate_rows` НЕ персистятся (`create` принимает только `parsed.nodes`) — строк с пустым кодом нет.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/ports.py backend/app/infrastructure/db/estimate_repository.py backend/tests/fakes.py backend/tests/test_estimate_matching_service.py
git commit -m "$(printf 'feat(estimates): bulk persistence классификации (excluded, охрана статуса) + чистка крошки\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 8: Оркестрация — шаг классификации в `EstimateMatchingService`

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py`
- Modify: `backend/app/api/deps.py`
- Test: `backend/tests/test_estimate_matching_service.py`

**Interfaces:**
- Consumes: `WorkTypeClassifier`, `classify_lexical`, `build_embedding_input`, `fetch_all_nodes`, `save_node_classifications`, `NodeToClassify`, `NodeClassification`, `WorkClass`.
- Produces: `EstimateMatchingService(..., classifier: WorkTypeClassifier)` с приватным `_classify_nodes(estimate_id)`, вызываемым в `match_estimate` сразу после `set_status(RUNNING)` и до `_embed_nodes`.

- [ ] **Step 1: Write the failing test**

```python
# добавить в backend/tests/test_estimate_matching_service.py
from app.domain.entities import TemplateArticle, WorkClass
from app.services.estimate_matching_service import EstimateMatchingService
from app.services.matching_service import MatchingService
from tests.fakes import FakeEmbedder, FakeRepository, FakeWorkTypeClassifier


def _two_node_estimate(repo: FakeEstimateRepository) -> int:
    # дерево: «1 Этап ЖК» (ORG) → «1.1 Устройство кровли» (WORK)
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [
            EstimateNode(code="1", name="1 Этап ЖК", parent_code=None,
                         section_type=None, embedding_input="1 Этап ЖК",
                         source_index=0, depth=1),
            EstimateNode(code="1.1", name="Устройство кровли", parent_code="1",
                         section_type=None, embedding_input="1 Этап ЖК. Устройство кровли",
                         source_index=1, depth=2),
        ],
    )
    return est.id


def _service(repo: FakeEstimateRepository, articles: FakeRepository) -> EstimateMatchingService:
    matcher = MatchingService(articles, embedder=None, llm_matcher=None, confidence_threshold=0.9)
    return EstimateMatchingService(
        matcher=matcher,
        embedder=FakeEmbedder(),
        estimates=repo,
        articles=articles,
        classifier=FakeWorkTypeClassifier(default=WorkClass.WORK),
    )


def test_classify_excludes_org_and_strips_breadcrumb() -> None:
    repo = FakeEstimateRepository()
    articles = FakeRepository(candidates=[])
    articles.add(TemplateArticle(article_code="1", name="Кровля",
                                 embedding_input="Кровля", embedding=[1.0, 1.0, 0.0]))
    eid = _two_node_estimate(repo)

    svc = _service(repo, articles)
    svc._classify_nodes(eid)  # noqa: SLF001 — целевой метод под тестом

    rows = {r.code: r for r in repo.get(eid, 1, is_admin=True).rows}
    # «1 Этап ЖК» — чистый каркас → ORG лексикой (без обращения к classifier) → excluded
    assert rows["1"].status == "excluded"
    # потомок-работа выжил, а ORG-предок вырезан из крошки
    assert rows["1.1"].status == "pending"
    assert rows["1.1"].embedding_input == "Устройство кровли"


def test_llm_org_verdict_on_mixed_also_excludes() -> None:
    # ORG из ВЕРДИКТА LLM (а не лексики) тоже обязан давать excluded.
    repo = FakeEstimateRepository()
    articles = FakeRepository(candidates=[])
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [EstimateNode(code="1", name="Гостиница Заря 1 Этап", parent_code=None,
                      section_type=None, embedding_input="Гостиница Заря 1 Этап",
                      source_index=0, depth=1)],
    )
    # «… 1 Этап» — смесь (оргтокен + голова «Гостиница») → UNSURE лексикой → LLM.
    clf = FakeWorkTypeClassifier(verdicts={"Гостиница Заря 1 Этап": WorkClass.ORG})
    matcher = MatchingService(articles, embedder=None, llm_matcher=None, confidence_threshold=0.9)
    svc = EstimateMatchingService(
        matcher=matcher, embedder=FakeEmbedder(), estimates=repo,
        articles=articles, classifier=clf,
    )
    svc._classify_nodes(est.id)  # noqa: SLF001
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "excluded"
    assert clf.calls  # LLM действительно вызван по смеси


def test_duplicate_code_excludes_only_scaffold() -> None:
    # Две строки с ОДНИМ кодом: работа + каркас. Класс по id, не по коду →
    # исключается только каркас, «Земляные работы» НЕ теряются молча.
    repo = FakeEstimateRepository()
    articles = FakeRepository(candidates=[])
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [
            EstimateNode(code="1.2", name="Земляные работы", parent_code="1",
                         section_type=None, embedding_input="Земляные работы",
                         source_index=0, depth=2),
            EstimateNode(code="1.2", name="1 Этап ЖК", parent_code="1",
                         section_type=None, embedding_input="1 Этап ЖК",
                         source_index=1, depth=2),
        ],
    )
    svc = _service(repo, articles)  # FakeWorkTypeClassifier(default=WorkClass.WORK)
    svc._classify_nodes(est.id)  # noqa: SLF001
    by_name = {r.name: r for r in repo.get(est.id, 1, is_admin=True).rows}
    assert by_name["Земляные работы"].status == "pending"   # работа выжила
    assert by_name["1 Этап ЖК"].status == "excluded"        # каркас исключён
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -k classify_excludes_org -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'classifier'`.

- [ ] **Step 3: Implement orchestration**

```python
# backend/app/services/estimate_matching_service.py

# (1) импорты:
from app.domain.classification import build_embedding_input, classify_lexical
from app.domain.entities import (
    ClassifiableNode, NodeClassification, NodeToClassify, WorkClass,
)
from app.domain.ports import (
    ArticleRepository, Embedder, EstimateRepository, WorkTypeClassifier,
)

# (2) __init__ — добавить параметр classifier и поле self._classifier = classifier

# (3) match_estimate — вставить ПЕРЕД self._embed_nodes(estimate_id):
        self._classify_nodes(estimate_id)

# (4) новый метод.
#  - Иерархия предков — по СЕГМЕНТАМ КОДА, точно как в estimate_parser.py:76-84
#    (крошка там тоже по segments, НЕ по parent_code) → совпадёт байт-в-байт.
#  - СОБСТВЕННЫЙ класс узла держим по n.id (cls_by_id), НЕ по коду: коды могут
#    дублироваться (парсер лишь предупреждает, но пишет обе строки), а ключ по коду
#    схлопнул бы их — и решение excluded утекло бы с одной строки на другую (тихий
#    пропуск работы). По коду — только представитель для имён/классов ПРЕДКОВ крошки
#    (первое вхождение, как name_by_code у парсера).
    def _classify_nodes(self, estimate_id: int) -> None:
        nodes = self._estimates.fetch_all_nodes(estimate_id)
        if not nodes:
            return
        # Представители по коду (первое вхождение) — только для крошки предков.
        name_by_code: dict[str, str] = {}
        repr_id_by_code: dict[str, int] = {}
        for n in nodes:
            name_by_code.setdefault(n.code, n.name)
            repr_id_by_code.setdefault(n.code, n.id)
        # Проход 1: лексика. Собственный класс — по id. UNSURE копим для LLM.
        cls_by_id: dict[int, WorkClass] = {}
        unsure: list[ClassifiableNode] = []
        for n in nodes:
            cls = classify_lexical(n.name)
            cls_by_id[n.id] = cls
            if cls is WorkClass.UNSURE:
                unsure.append(n)
        # Проход 1b: LLM по неоднозначным (UNSURE-вердикт остаётся = keep).
        if unsure:
            items = [
                NodeToClassify(n.name, self._ancestor_names(n.code, name_by_code))
                for n in unsure
            ]
            for n, verdict in zip(unsure, self._classifier.classify(items), strict=True):
                cls_by_id[n.id] = verdict
        # Проход 2: собрать результаты + пересборка крошки (ORG-предки выброшены) → bulk-запись.
        results: list[NodeClassification] = []
        for n in nodes:
            ancestors = [
                (name_by_code[a], cls_by_id[repr_id_by_code[a]])
                for a in self._ancestor_codes(n.code)
                if a in name_by_code
            ]
            crumb = build_embedding_input(n.name, ancestors)
            # ORG из ЛЮБОГО источника (лексика row-2 ИЛИ вердикт LLM) → excluded.
            # Класс берём по n.id — дубли кода НЕ схлопываются.
            results.append(
                NodeClassification(
                    node_id=n.id,
                    excluded=cls_by_id[n.id] is WorkClass.ORG,
                    embedding_input=crumb,
                )
            )
        self._estimates.save_node_classifications(results)  # один commit, охрана статуса

    @staticmethod
    def _ancestor_codes(code: str) -> list[str]:
        segs = code.split(".")
        return [".".join(segs[:i]) for i in range(1, len(segs))]  # root..parent, без узла

    def _ancestor_names(self, code: str, name_by_code: dict[str, str]) -> tuple[str, ...]:
        return tuple(name_by_code[a] for a in self._ancestor_codes(code) if a in name_by_code)
```

```python
# backend/app/api/deps.py

# (1) импорты:
from app.infrastructure.ai.anthropic_classifier import AnthropicWorkClassifier
from app.domain.ports import WorkTypeClassifier  # к существующим

# (2) синглтон-фабрика:
@lru_cache
def get_work_classifier() -> WorkTypeClassifier:
    settings = get_settings()
    return AnthropicWorkClassifier(
        api_key=settings.anthropic_api_key,
        model=settings.classifier_model,
        batch_size=settings.classifier_batch_size,
        timeout_s=settings.ai_call_timeout_s,
        retry_budget=settings.transient_retry_budget,
    )

# (3) в build_estimate_matching_service — добавить аргумент classifier=get_work_classifier()
```

> **Существующие тесты сервиса:** во всех местах, где в тестах конструируется `EstimateMatchingService(...)`, добавить `classifier=FakeWorkTypeClassifier(default=WorkClass.WORK)` (иначе `TypeError`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -v`
Expected: PASS (включая существующие тесты сервиса).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/estimate_matching_service.py backend/app/api/deps.py backend/tests/test_estimate_matching_service.py
git commit -m "$(printf 'feat(estimates): шаг классификации узлов до эмбеддинга + чистка крошки\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 9: Экспорт — «Статья СМР» пуста для excluded (характеризующий тест)

**Files:**
- Modify/Create: `backend/tests/test_estimate_export_service.py`

**Interfaces:**
- Consumes: `EstimateExportService._cell_value` (уже отдаёт `""` для всего, кроме `confident`/`confirmed`/`overridden`). Цель — зафиксировать, что `status='excluded'` экспортится пустым; правок кода НЕ требуется.

- [ ] **Step 1: Write the (characterization) test**

```python
# backend/tests/test_estimate_export_service.py (добавить; если файла нет — создать с шапкой)
from __future__ import annotations

from app.domain.entities import StoredEstimateRow
from app.services.estimate_export_service import EstimateExportService


def _row(status: str) -> StoredEstimateRow:
    return StoredEstimateRow(
        id=1, code="1", name="1 Этап ЖК", parent_code=None, section_type=None,
        depth=1, embedding_input="1 Этап ЖК", source_index=0, status=status,
    )


def test_excluded_row_exports_empty_article() -> None:
    assert EstimateExportService._cell_value(_row("excluded")) == ""  # noqa: SLF001
```

- [ ] **Step 2: Run test to verify it (already) passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_export_service.py -k excluded -v`
Expected: PASS (поведение `_cell_value` уже верное — тест фиксирует его как контракт).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_estimate_export_service.py
git commit -m "$(printf 'test(estimates): excluded → пустая «Статья СМР» при выгрузке\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Финальная проверка

- [ ] **Полный прогон бэк-тестов:** `cd backend && PYTHONIOENCODING=utf-8 uv run pytest -q` — всё зелёное.
- [ ] **Линт:** `cd backend && uv run ruff check .` — чисто.
- [ ] **Manual verification (реальный репозиторий + LLM):**
  1. Поднять бэк (`just dev-back`), загрузить `temp/Смета — копия.xlsx`.
  2. Дождаться статуса `ready`/`partial_error` (НЕ зависает — excluded не в знаменателе).
  3. В выдаче `GET /api/estimates/{id}`: узлы «1 Этап ЖК», «Корпус …» имеют `status='excluded'`; «I и 2 Этапы БЦ и ЖК» больше НЕ матчится в «Прочее».
  4. У выживших работных узлов `embedding_input` не содержит «Этап»/«Корпус»/«ЖК»/«БЦ» из предков.
  5. Выгрузка: у excluded-строк столбец «Статья СМР» пуст.
  6. Краевой случай: смета целиком из орг-узлов → `ready`, `nodes_count=0` —
     фронтовый список и экран проверки не падают на «готово, пусто».

## DoD-гейты из спеки (повторная проверка глазами)

- [ ] Чистый каркас → ORG лексикой без LLM → `status='excluded'`; смесь → UNSURE/WORK, никогда ошибочный ORG.
- [ ] Крошка выживших узлов без оргтокенов предков.
- [ ] ORG исключены обратимо (строки не удалены, `status='excluded'`); «Статья СМР» пуста.
- [ ] Битый JSON классификатора → UNSURE, не ORG.

---

## Self-Review (заполняется автором плана)

**Spec coverage:** каскад (Tasks 1–3), чистка крошки (Task 4), порт+адаптер (Tasks 5–6), persistence excluded + исключение из выборок/счётчиков/`nodes_count` (Task 7), оркестрация + интеграционный стык знаменателя (Task 8), пустой экспорт (Task 9) — покрыто. Колонка/миграция/API-поле выпали по решению «только status='excluded'».
**Placeholder scan:** код приведён полностью; «# (N) …» — точечные правки существующих функций с указанием места.
**Type consistency:** `WorkClass`/`NodeToClassify`/`ClassifiableNode`/`NodeClassification` определены в Tasks 3/5/7 до использования в Task 8; `classify(items)->list[WorkClass]` единообразно; `save_node_classifications(list[NodeClassification])` совпадает в порту, репозитории и фейке; `fetch_matchable_nodes`/`count_*` не трогаются (проверено в коде) — `excluded` вне их наборов статусов.
