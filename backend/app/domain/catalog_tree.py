"""Чистый обход дерева справочника (parent_id) — крошки статей для UI.

Живёт в домене: и SQL-репозиторий, и фейк тестов зовут ЭТУ функцию —
логика обхода существует в одном месте.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_MAX_DEPTH = 20  # защита от цикла parent_id (реальное дерево — 2-3 уровня)


def ancestor_names_by_ids(
    nodes: Mapping[int, tuple[str, int | None]],
    article_ids: Sequence[int],
) -> dict[int, list[str]]:
    """Имена предков root→parent (без самой статьи) для каждого запрошенного id.

    nodes — карта id -> (name, parent_id). Неизвестные id опускаются из ответа;
    битая parent-ссылка обрывает цепочку (возвращаем то, что успели собрать).
    """
    out: dict[int, list[str]] = {}
    for aid in article_ids:
        node = nodes.get(aid)
        if node is None:
            continue
        chain: list[str] = []
        cur = node[1]
        while cur is not None and len(chain) < _MAX_DEPTH:
            parent = nodes.get(cur)
            if parent is None:
                break
            chain.append(parent[0])
            cur = parent[1]
        out[aid] = list(reversed(chain))
    return out
