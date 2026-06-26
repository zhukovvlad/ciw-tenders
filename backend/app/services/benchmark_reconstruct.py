"""Реконструкция узлов сметы из seed-узлов бенчмарка для прогона через пайплайн.

Инвариант: тот же code/parent_code/depth, что у EstimateParser. Крошку (embedding_input)
пересобирает сам пайплайн на шаге классификации, поэтому здесь — плейсхолдер.
"""

from __future__ import annotations

from app.domain.entities import BenchmarkNodeSeed, EstimateNode


def reconstruct_nodes(seeds: list[BenchmarkNodeSeed]) -> list[EstimateNode]:
    nodes: list[EstimateNode] = []
    for seed in seeds:
        segments = seed.code.split(".")
        parent_code = ".".join(segments[:-1]) or None
        nodes.append(
            EstimateNode(
                code=seed.code,
                name=seed.name,
                parent_code=parent_code,
                section_type=None,  # в матчинге не используется (org-filter спека)
                embedding_input=seed.name,  # плейсхолдер; пайплайн пересоберёт крошку
                source_index=seed.source_index,
                depth=len(segments),
            )
        )
    return nodes
