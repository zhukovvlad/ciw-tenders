from __future__ import annotations

import logging

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.infrastructure.ai.llm_matching_common import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_choice,
)


def _cand(aid: int, code: str, name: str, score: float = 0.5) -> ArticleCandidate:
    return ArticleCandidate(
        TemplateArticle(id=aid, article_code=code, name=name, embedding_input=f"ei {code}"),
        score,
    )


def _three() -> list[ArticleCandidate]:
    return [
        _cand(1, "08.03.01", "Кладка"),
        _cand(2, "08.03.02", "Штукатурка"),
        _cand(3, "08.03.03", "Окраска"),
    ]


def test_build_user_prompt_lists_names_without_code() -> None:
    prompt = build_user_prompt("кладка кирпича", _three())
    assert "1. Кладка" in prompt and "2. Штукатурка" in prompt
    assert "08.03.01" not in prompt  # код НЕ утекает в листинг


def test_system_prompt_requires_row_number_and_refusal_channel() -> None:
    assert "0" in SYSTEM_PROMPT  # канал отказа задан


def test_plain_number_picks_candidate() -> None:
    assert parse_choice("2", _three()).article_code == "08.03.02"


def test_wrapped_answer_picks_candidate() -> None:
    assert parse_choice("The best match is option 2.", _three()).article_code == "08.03.02"


def test_zero_is_refusal_not_last_candidate() -> None:
    # off-by-one guard: "0" → None, НЕ candidates[-1]
    assert parse_choice("0", _three()) is None


def test_zero_does_not_warn(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert parse_choice("0", _three()) is None
    assert caplog.records == []  # легитимный отказ ≠ сбой формата


def test_code_like_answer_out_of_range_is_none(caplog) -> None:
    # модель вернула код "08.03.01" при top_k=3 → первый int 8 → вне диапазона → None
    with caplog.at_level(logging.WARNING):
        assert parse_choice("08.03.01", _three()) is None
    assert caplog.records  # это сбой формата → warning


def test_negative_number_is_none_not_misroute(caplog) -> None:
    # "-1" не должен мапиться на candidates[0]: знаковый токен → вне диапазона → None (warning)
    with caplog.at_level(logging.WARNING):
        assert parse_choice("-1", _three()) is None
    assert caplog.records


def test_garbage_is_none_with_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert parse_choice("не знаю", _three()) is None
    assert caplog.records


def test_empty_is_none_without_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert parse_choice("", _three()) is None
    assert caplog.records == []
