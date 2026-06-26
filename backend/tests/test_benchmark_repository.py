from __future__ import annotations

from app.domain.entities import BenchmarkNodeSeed
from app.infrastructure.db.benchmark_repository import model_to_seed, seed_to_model
from app.infrastructure.db.models import BenchmarkNodeModel


def testseed_to_model_maps_all_fields():
    seed = BenchmarkNodeSeed(
        code="6.3.1", name="Подсистема", source_index=42,
        expected_kind="matchable", expected_article_code="6.3.1",
        expected_article_name="Устройство подсистемы фасада",
    )
    m = seed_to_model(seed, benchmark_id=7)
    assert m.benchmark_id == 7
    assert m.code == "6.3.1"
    assert m.source_index == 42
    assert m.expected_kind == "matchable"
    assert m.expected_article_code == "6.3.1"
    assert m.expected_article_name == "Устройство подсистемы фасада"


def testmodel_to_seed_roundtrip():
    m = BenchmarkNodeModel(
        benchmark_id=1, source_index=3, code="10", name="Инженерные системы",
        expected_kind="no_article", expected_article_code=None,
        expected_article_name=None,
    )
    seed = model_to_seed(m)
    assert seed.code == "10"
    assert seed.expected_kind == "no_article"
    assert seed.expected_article_code is None
