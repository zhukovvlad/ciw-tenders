from __future__ import annotations

import io

import openpyxl

from app.domain.entities import BenchmarkNodeSeed
from app.services.benchmark_reconstruct import reconstruct_nodes
from app.services.estimate_parser import EstimateParser


def _xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["№ раздела", "Наименование раздела / позиции", "Вид раздела"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_reconstruct_matches_parser_codes_and_hierarchy():
    rows = [
        ["1", "Подготовительные работы", "СМР"],
        ["1.1", "Мобилизация", None],
        ["1.1.1", "Снос", None],
    ]
    parsed = EstimateParser().parse(_xlsx_bytes(rows))
    seeds = [
        BenchmarkNodeSeed(code=n.code, name=n.name, source_index=n.source_index,
                          expected_kind="matchable", expected_article_code=None,
                          expected_article_name=None)
        for n in parsed.nodes
    ]
    recon = reconstruct_nodes(seeds)
    assert [n.code for n in recon] == [n.code for n in parsed.nodes]
    assert [n.parent_code for n in recon] == [n.parent_code for n in parsed.nodes]
    assert [n.depth for n in recon] == [n.depth for n in parsed.nodes]


def test_reconstruct_parent_and_depth_from_code():
    seeds = [
        BenchmarkNodeSeed("4.1.2", "Ж/Б конструкции", 5, "matchable", None, None),
    ]
    node = reconstruct_nodes(seeds)[0]
    assert node.parent_code == "4.1"
    assert node.depth == 3
    assert node.embedding_input  # непустой плейсхолдер
