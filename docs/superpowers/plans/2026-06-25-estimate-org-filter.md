# Фильтрация организационных заголовков (lean v1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** До эмбеддинга классифицировать узлы сметы в WORK/ORG/UNSURE по смыслу имени, обратимо исключить ORG из эмбеддинга/матчинга и вырезать ORG-предков из крошки `embedding_input`.

**Architecture:** Чистый каскад «лексика → LLM» в доменном слое + дешёвый LLM-классификатор за портом в infrastructure. Оркестрация — новый шаг в `EstimateMatchingService` до эмбеддинга. Метка `node_class` хранится в `estimate_rows`, питает гейт матчинга и пересборку крошки.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy + pgvector, Anthropic SDK (Haiku-класс), Alembic, pytest.

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

## File Structure

| Файл | Ответственность | Действие |
|---|---|---|
| `backend/app/domain/classification.py` | Лексика: оргтокены, `has_work_word`, `classify_lexical`, `build_embedding_input` | Create |
| `backend/app/domain/entities.py` | `WorkClass`, `NodeToClassify`, `EstimateRowStatus.EXCLUDED`, `StoredEstimateRow.node_class` | Modify |
| `backend/app/domain/ports.py` | Порт `WorkTypeClassifier` | Modify |
| `backend/app/infrastructure/ai/anthropic_classifier.py` | LLM-адаптер классификатора + промпт/парсинг | Create |
| `backend/app/core/config.py` | `classifier_model`, `classifier_batch_size` | Modify |
| `backend/app/infrastructure/db/models.py` | колонка `node_class` | Modify |
| `backend/alembic/versions/0006_estimate_node_class.py` | миграция | Create |
| `backend/app/infrastructure/db/estimate_repository.py` | persistence классификации + исключение ORG в запросах | Modify |
| `backend/app/services/estimate_matching_service.py` | шаг классификации + пересборка крошки | Modify |
| `backend/app/api/deps.py` | DI классификатора | Modify |
| `backend/app/api/schemas.py` | `node_class` в `EstimateRowOut` | Modify |
| `backend/tests/fakes.py` | `FakeWorkTypeClassifier` + зеркало изменений репозитория | Modify |
| `backend/tests/test_classification.py` | юнит-тесты домена | Create |
| `backend/tests/test_anthropic_classifier.py` | юнит-тесты адаптера | Create |
| `backend/tests/test_estimate_matching_service.py` | тесты оркестрации | Modify |

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
    "этап", "очеред", "пусков", "корпус", "литер", "секци", "объект", "блок-секци",
)
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
_STOPWORDS = frozenset(
    {
        "прочее", "прочие", "работы", "работ", "и", "в", "с", "по", "на",
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
    """Класс узла сметы по смыслу имени (для фильтрации оргзаголовков)."""

    WORK = "work"      # вид работ — матчится
    ORG = "org"        # организационный заголовок — исключается обратимо
    UNSURE = "unsure"  # неоднозначно — трактуем как WORK (асимметрия ошибок)
```

```python
# backend/app/domain/classification.py — добавить
from app.domain.entities import WorkClass  # noqa: E402  (в начало файла, к импортам)


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


def parse_classifications(text: str, n: int) -> list[WorkClass]:
    """Строгий парс. Любая аномалия (битый JSON, не та длина) → всё UNSURE."""
    try:
        data = json.loads(text)
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
Expected: PASS (4 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/infrastructure/ai/anthropic_classifier.py backend/tests/test_anthropic_classifier.py
git commit -m "$(printf 'feat(classify): Anthropic LLM-классификатор (батч, строгий JSON, фолбэк UNSURE)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 7: Схема БД — колонка `node_class` + статус `excluded`

**Files:**
- Modify: `backend/app/domain/entities.py`
- Modify: `backend/app/infrastructure/db/models.py`
- Create: `backend/alembic/versions/0006_estimate_node_class.py`

**Interfaces:**
- Produces: `EstimateRowStatus.EXCLUDED = "excluded"`; `StoredEstimateRow.node_class: str = "unsure"`; колонка БД `estimate_rows.node_class VARCHAR(16) NOT NULL DEFAULT 'unsure'`.

- [ ] **Step 1: Добавить статус и поле сущности**

```python
# backend/app/domain/entities.py — в EstimateRowStatus
    EXCLUDED = "excluded"  # node_class=ORG: исключён из эмбеддинга/матчинга (обратимо)
```

```python
# backend/app/domain/entities.py — в StoredEstimateRow, после status
    node_class: str = "unsure"
```

- [ ] **Step 2: Добавить колонку в ORM-модель**

```python
# backend/app/infrastructure/db/models.py — в EstimateRowModel, после status
    node_class: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unsure")
```

- [ ] **Step 3: Написать миграцию**

```python
# backend/alembic/versions/0006_estimate_node_class.py
"""estimate node_class column

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL DEFAULT 'unsure' — metadata-only на Postgres; существующие строки бэкфиллятся.
    op.execute(
        "ALTER TABLE estimate_rows "
        "ADD COLUMN node_class VARCHAR(16) NOT NULL DEFAULT 'unsure'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE estimate_rows DROP COLUMN IF EXISTS node_class")
```

- [ ] **Step 4: Применить миграцию и проверить импорт модели**

Run: `just migrate`
Expected: `Running upgrade 0005 -> 0006`.
Run: `cd backend && PYTHONIOENCODING=utf-8 uv run python -c "from app.infrastructure.db.models import EstimateRowModel; print(EstimateRowModel.__table__.c.node_class.type)"`
Expected: `VARCHAR(16)`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/entities.py backend/app/infrastructure/db/models.py backend/alembic/versions/0006_estimate_node_class.py
git commit -m "$(printf 'feat(estimates): колонка node_class + статус excluded (миграция 0006)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 8: Репозиторий — persistence классификации + исключение ORG

**Files:**
- Modify: `backend/app/domain/entities.py` (сущность `ClassifiableNode`)
- Modify: `backend/app/domain/ports.py` (новые методы `EstimateRepository`)
- Modify: `backend/app/infrastructure/db/estimate_repository.py`
- Modify: `backend/tests/fakes.py` (зеркало в `FakeEstimateRepository`)
- Test: `backend/tests/test_estimate_matching_service.py` (через фейк — Step 1)

**Interfaces:**
- Produces:
  - `ClassifiableNode(id: int, code: str, name: str)`.
  - `EstimateRepository.fetch_all_nodes(estimate_id) -> list[ClassifiableNode]` (все узлы, по возрастанию `source_index`).
  - `EstimateRepository.save_node_classification(node_id, node_class: str, embedding_input: str) -> None` (пишет `node_class`; при `node_class=='org'` ставит `status='excluded'`; иначе не трогает status; всегда обновляет `embedding_input`).
  - `fetch_unembedded_nodes`/`fetch_matchable_nodes`/`count_unfinished_nodes`/`count_node_errors` исключают `node_class='org'`.
  - `list_for_owner`: `nodes_count` считает только `node_class != 'org'`.

- [ ] **Step 1: Write the failing test (через фейк)**

```python
# добавить в backend/tests/test_estimate_matching_service.py
from app.domain.entities import EstimateNode, NewEstimate
from tests.fakes import FakeEstimateRepository


def _seed_one(repo: FakeEstimateRepository, name: str) -> int:
    est = repo.create(
        NewEstimate(user_id=1, filename="f.xlsx", original_object_key="k"),
        [EstimateNode(code="1", name=name, parent_code=None, section_type=None,
                      embedding_input=name, source_index=0, depth=1)],
    )
    return est.rows[0].id


def test_fake_repo_excludes_org_from_matchable_and_counts() -> None:
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "1 Этап ЖК")
    repo.save_node_classification(nid, "org", "1 Этап ЖК")
    # ORG исключён из всех рабочих выборок и счётчиков
    assert repo.fetch_unembedded_nodes(1, after_id=0, limit=10) == []
    assert repo.count_unfinished_nodes(1) == 0
    assert repo.list_for_owner(1, is_admin=True)[0].nodes_count == 0


def test_fake_repo_save_classification_rewrites_breadcrumb() -> None:
    repo = FakeEstimateRepository()
    nid = _seed_one(repo, "x")
    repo.save_node_classification(nid, "work", "Чистая крошка")
    pend = repo.fetch_unembedded_nodes(1, after_id=0, limit=10)
    assert pend[0].embedding_input == "Чистая крошка"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -k fake_repo -v`
Expected: FAIL — `AttributeError: 'FakeEstimateRepository' object has no attribute 'save_node_classification'`.

- [ ] **Step 3a: Сущность + порт**

```python
# backend/app/domain/entities.py — добавить
@dataclass(frozen=True, slots=True)
class ClassifiableNode:
    """Узел для прохода классификации: id + код (для дерева) + имя."""

    id: int
    code: str
    name: str
```

```python
# backend/app/domain/ports.py — добавить в EstimateRepository (импортнуть ClassifiableNode)
    @abstractmethod
    def fetch_all_nodes(self, estimate_id: int) -> list[ClassifiableNode]:
        """Все узлы сметы (id, code, name) по возрастанию source_index."""
        ...

    @abstractmethod
    def save_node_classification(
        self, node_id: int, node_class: str, embedding_input: str
    ) -> None:
        """Пишет node_class + новую крошку. ORG → status='excluded' (обратимо)."""
        ...
```

- [ ] **Step 3b: Реализация в SqlAlchemy-репозитории**

```python
# backend/app/infrastructure/db/estimate_repository.py

# (1) в _row_to_entity(...) добавить в StoredEstimateRow(...):
#         node_class=m.node_class,

# (2) fetch_all_nodes:
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

# (3) save_node_classification:
    def save_node_classification(
        self, node_id: int, node_class: str, embedding_input: str
    ) -> None:
        values: dict = {"node_class": node_class, "embedding_input": embedding_input}
        if node_class == "org":
            values["status"] = "excluded"
        self._session.execute(
            update(EstimateRowModel).where(EstimateRowModel.id == node_id).values(**values)
        )
        self._session.commit()

# (4) в fetch_unembedded_nodes — добавить в .where(...):
#         EstimateRowModel.node_class != "org",

# (5) в fetch_matchable_nodes — добавить в .where(...):
#         EstimateRowModel.node_class != "org",

# (6) в count_node_errors и count_unfinished_nodes — добавить в .where(...):
#         EstimateRowModel.node_class != "org",

# (7) в list_for_owner — counts subquery считает только матчируемые:
#     .where(EstimateRowModel.node_class != "org")  перед .group_by(...)
```

Импортировать `ClassifiableNode` в шапке файла из `app.domain.entities`.

- [ ] **Step 3c: Зеркало в фейке**

```python
# backend/tests/fakes.py — FakeEstimateRepository

# (1) в create(): в self.nodes[nid] добавить "node_class": "unsure"
#     и в StoredEstimateRow(...) добавить node_class="unsure"
# (2) в _row_entity(...) StoredEstimateRow(...) добавить node_class=n["node_class"]

    def fetch_all_nodes(self, estimate_id: int):  # noqa: ANN201
        from app.domain.entities import ClassifiableNode

        rows = sorted(
            (n for n in self.nodes.values() if n["estimate_id"] == estimate_id),
            key=lambda n: n["id"],
        )
        # code/name берём из StoredEstimateRow базы
        base = {r.id: r for e in self.estimates.values() for r in e.rows}
        return [ClassifiableNode(id=n["id"], code=base[n["id"]].code, name=base[n["id"]].name)
                for n in rows]

    def save_node_classification(self, node_id: int, node_class: str, embedding_input: str) -> None:
        n = self.nodes[node_id]
        n["node_class"] = node_class
        n["embedding_input"] = embedding_input
        if node_class == "org":
            n["status"] = "excluded"

# (3) добавить условие n["node_class"] != "org" в:
#     fetch_unembedded_nodes, fetch_matchable_nodes, count_node_errors, count_unfinished_nodes
# (4) list_for_owner: nodes_count = sum(1 for r in e.rows if self.nodes[r.id]["node_class"] != "org")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -k fake_repo -v`
Expected: PASS (2 cases).

> **Note (реальный репозиторий):** `SqlAlchemyEstimateRepository` юнит-тестами не покрыт (нет БД в юнитах). Изменения (3b) зеркалят логику фейка; верификация — `just migrate` (Task 7) + ручной прогон сметы (раздел «Manual verification»).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/ports.py backend/app/infrastructure/db/estimate_repository.py backend/tests/fakes.py backend/tests/test_estimate_matching_service.py
git commit -m "$(printf 'feat(estimates): persistence классификации + исключение ORG из матчинга/счётчиков\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 9: Оркестрация — шаг классификации в `EstimateMatchingService`

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py`
- Modify: `backend/app/api/deps.py`
- Test: `backend/tests/test_estimate_matching_service.py`

**Interfaces:**
- Consumes: `WorkTypeClassifier`, `classify_lexical`, `build_embedding_input`, `fetch_all_nodes`, `save_node_classification`, `NodeToClassify`, `ClassifiableNode`, `WorkClass`.
- Produces: `EstimateMatchingService(..., classifier: WorkTypeClassifier)` с приватным `_classify_nodes(estimate_id)`, вызываемым в `match_estimate` сразу после `set_status(RUNNING)` и до `_embed_nodes`.

- [ ] **Step 1: Write the failing test**

```python
# добавить в backend/tests/test_estimate_matching_service.py
from app.domain.entities import WorkClass
from app.services.estimate_matching_service import EstimateMatchingService
from app.services.matching_service import MatchingService
from tests.fakes import (
    FakeEmbedder, FakeRepository, FakeWorkTypeClassifier,
)


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
    articles = FakeRepository(candidates=[])  # пустой каталог → readiness даст gate? см. ниже
    # заполняем каталог 1 статьёй с эмбеддингом, чтобы пройти gate
    from app.domain.entities import TemplateArticle
    art = articles.add(TemplateArticle(article_code="1", name="Кровля",
                                       embedding_input="Кровля", embedding=[1.0, 1.0, 0.0]))
    eid = _two_node_estimate(repo)

    svc = _service(repo, articles)
    svc._classify_nodes(eid)  # noqa: SLF001 — целевой метод под тестом

    rows = {r.code: r for r in repo.get(eid, 1, is_admin=True).rows}
    # «1 Этап ЖК» — чистый каркас → ORG лексикой (без обращения к classifier)
    assert rows["1"].node_class == "org"
    assert rows["1"].status == "excluded"
    # потомок-работа выжил, а ORG-предок вырезан из крошки
    assert rows["1.1"].node_class == "work"
    assert rows["1.1"].embedding_input == "Устройство кровли"
    _ = art
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -k classify_excludes_org -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'classifier'`.

- [ ] **Step 3: Implement orchestration**

```python
# backend/app/services/estimate_matching_service.py

# (1) импорты:
from app.domain.classification import build_embedding_input, classify_lexical
from app.domain.entities import NodeToClassify, WorkClass
from app.domain.ports import (
    ArticleRepository, Embedder, EstimateRepository, WorkTypeClassifier,
)

# (2) __init__ — добавить параметр и поле:
    def __init__(self, matcher, embedder, estimates, articles, classifier):  # типы как в сигнатурах
        ...
        self._classifier = classifier

# (3) match_estimate — вставить ПЕРЕД self._embed_nodes(estimate_id):
        self._classify_nodes(estimate_id)

# (4) новый метод:
    def _classify_nodes(self, estimate_id: int) -> None:
        nodes = self._estimates.fetch_all_nodes(estimate_id)
        if not nodes:
            return
        name_by_code = {n.code: n.name for n in nodes}
        # Проход 1: лексика. UNSURE копим для LLM.
        cls_by_code: dict[str, WorkClass] = {}
        unsure: list[tuple[str, NodeToClassify]] = []  # (code, item)
        for n in nodes:
            cls = classify_lexical(n.name)
            cls_by_code[n.code] = cls
            if cls is WorkClass.UNSURE:
                unsure.append((n.code, NodeToClassify(n.name, self._ancestor_names(n.code, name_by_code))))
        # Проход 1b: LLM по неоднозначным (UNSURE-вердикт остаётся = keep).
        if unsure:
            verdicts = self._classifier.classify([item for _, item in unsure])
            for (code, _), verdict in zip(unsure, verdicts, strict=True):
                cls_by_code[code] = verdict
        # Проход 2: persist класс + пересборка крошки (ORG-предки выброшены).
        id_by_code = {n.code: n.id for n in nodes}
        for n in nodes:
            cls = cls_by_code[n.code]
            ancestors = [
                (name_by_code[a], cls_by_code[a]) for a in self._ancestor_codes(n.code)
                if a in name_by_code
            ]
            crumb = build_embedding_input(n.name, ancestors)
            self._estimates.save_node_classification(id_by_code[n.code], str(cls), crumb)

    @staticmethod
    def _ancestor_codes(code: str) -> list[str]:
        segs = code.split(".")
        return [".".join(segs[:i]) for i in range(1, len(segs))]  # root..parent, без самого узла

    def _ancestor_names(self, code: str, name_by_code: dict[str, str]) -> tuple[str, ...]:
        return tuple(name_by_code[a] for a in self._ancestor_codes(code) if a in name_by_code)
```

```python
# backend/app/api/deps.py

# (1) импорт:
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

# (3) в build_estimate_matching_service — добавить аргумент:
    return EstimateMatchingService(
        matcher=matcher,
        embedder=get_embedder(),
        estimates=estimates,
        articles=articles,
        classifier=get_work_classifier(),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -v`
Expected: PASS (включая существующие тесты сервиса — проверить, что не сломаны; во всех конструкторах сервиса в тестах добавить `classifier=...`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/estimate_matching_service.py backend/app/api/deps.py backend/tests/test_estimate_matching_service.py
git commit -m "$(printf 'feat(estimates): шаг классификации узлов до эмбеддинга + чистка крошки\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 10: API — `node_class` в выдаче строк

**Files:**
- Modify: `backend/app/api/schemas.py`
- Test: `backend/tests/test_classification.py` (юнит на маппинг DTO) или существующий API-тест

**Interfaces:**
- Consumes: `StoredEstimateRow.node_class`.
- Produces: `EstimateRowOut.node_class: str` (фронт рисует ORG отдельной свёрнутой корзиной).

- [ ] **Step 1: Write the failing test**

```python
# добавить в backend/tests/test_classification.py
from datetime import datetime, timezone

from app.api.schemas import EstimateRowOut
from app.domain.entities import StoredEstimateRow


def test_estimate_row_out_carries_node_class() -> None:
    row = StoredEstimateRow(
        id=1, code="1", name="1 Этап ЖК", parent_code=None, section_type=None,
        depth=1, embedding_input="1 Этап ЖК", source_index=0, status="excluded",
        node_class="org",
    )
    assert EstimateRowOut.from_entity(row).node_class == "org"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k node_class -v`
Expected: FAIL — `AttributeError` / валидатор: нет поля `node_class`.

- [ ] **Step 3: Implement**

```python
# backend/app/api/schemas.py — в EstimateRowOut, после status:
    node_class: str = "unsure"

# и в from_entity(...): добавить node_class=r.node_class,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_classification.py -k node_class -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/schemas.py backend/tests/test_classification.py
git commit -m "$(printf 'feat(estimates): node_class в EstimateRowOut\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Финальная проверка

- [ ] **Полный прогон бэк-тестов:** `cd backend && PYTHONIOENCODING=utf-8 uv run pytest -q` — всё зелёное.
- [ ] **Линт:** `cd backend && uv run ruff check .` — чисто.
- [ ] **Manual verification (реальный репозиторий + LLM):**
  1. `just migrate` применён (0006).
  2. Поднять бэк (`just dev-back`), загрузить `temp/Смета — копия.xlsx`.
  3. Дождаться статуса `ready`/`partial_error` (НЕ зависает — ORG не в знаменателе).
  4. В выдаче `GET /api/estimates/{id}`: узлы «1 Этап ЖК», «Корпус …» имеют `node_class='org'`, `status='excluded'`; «I и 2 Этапы БЦ и ЖК» больше НЕ матчится в «Прочее».
  5. У выживших работных узлов `embedding_input` не содержит «Этап»/«Корпус»/«ЖК»/«БЦ» из предков.

## DoD-гейты из спеки (повторная проверка глазами)

- [ ] Чистый каркас → ORG лексикой без LLM; смесь → UNSURE/WORK, никогда ошибочный ORG.
- [ ] Крошка выживших узлов без оргтокенов предков.
- [ ] ORG исключены обратимо (строки не удалены, `status='excluded'`), отдаются в API.
- [ ] Битый JSON классификатора → UNSURE, не ORG.

---

## Self-Review (заполняется автором плана)

**Spec coverage:** каскад (Tasks 1–3), чистка крошки (Task 4), порт+адаптер (Tasks 5–6), node_class+excluded+счётчики (Tasks 7–9), API (Task 10), интеграционный стык знаменателя (Task 8 счётчики + Task 9 порядок) — покрыто.
**Placeholder scan:** код приведён полностью в каждом шаге; «// (N) …» — точечные правки существующих функций с указанием места.
**Type consistency:** `WorkClass`/`NodeToClassify`/`ClassifiableNode` определены в Tasks 3/5/8 до их использования в Task 9; `classify(items)->list[WorkClass]` единообразно; `save_node_classification(node_id, node_class, embedding_input)` совпадает в порту, репозитории и фейке.
