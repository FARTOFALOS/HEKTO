"""
Tests for the HEKTO chunk role classifier (src/classify.py).
"""

from __future__ import annotations

import pytest

from src.classify import classify_chunk_role, detect_chain_open, detect_chain_close


class TestClassifyChunkRole:
    """Unit tests for keyword-based role classification."""

    def test_analysis_keywords(self) -> None:
        assert classify_chunk_role("вижу сопротивление на уровне 42000") == "analysis"

    def test_expectation_keywords(self) -> None:
        assert classify_chunk_role("думаю пойдёт вверх скорее всего") == "expectation"

    def test_doubt_keywords(self) -> None:
        assert classify_chunk_role("не уверен стоит ли входить рискованно") == "doubt"

    def test_hold_keywords(self) -> None:
        assert classify_chunk_role("подержу ещё чуть-чуть не выхожу") == "hold"

    def test_exit_keywords(self) -> None:
        assert classify_chunk_role("закрыл позицию вышел") == "exit"

    def test_reflection_keywords(self) -> None:
        assert classify_chunk_role("надо было раньше выйти зря вошёл") == "reflection"

    def test_no_keywords_returns_other(self) -> None:
        assert classify_chunk_role("привет как дела") == "other"

    def test_empty_text_returns_other(self) -> None:
        assert classify_chunk_role("") == "other"

    def test_mixed_keywords_highest_wins(self) -> None:
        # "doubt" has 2 keywords, "analysis" has 1
        role = classify_chunk_role("не уверен рискованно но вижу сетап")
        assert role == "doubt"

    def test_case_insensitive(self) -> None:
        assert classify_chunk_role("ВИЖУ СОПРОТИВЛЕНИЕ") == "analysis"


class TestChainTriggers:
    """Tests for chain open/close detection."""

    def test_chain_open_смотрю(self) -> None:
        assert detect_chain_open("смотрю на график") is True

    def test_chain_open_вижу_сетап(self) -> None:
        assert detect_chain_open("вижу сетап на биткоине") is True

    def test_chain_open_анализирую(self) -> None:
        assert detect_chain_open("анализирую текущую ситуацию") is True

    def test_chain_open_no_trigger(self) -> None:
        assert detect_chain_open("просто мысли вслух") is False

    def test_chain_open_empty(self) -> None:
        assert detect_chain_open("") is False

    def test_chain_close_закрыл(self) -> None:
        assert detect_chain_close("закрыл позицию") is True

    def test_chain_close_вышел(self) -> None:
        assert detect_chain_close("вышел из сделки") is True

    def test_chain_close_стоп(self) -> None:
        assert detect_chain_close("стоп сработал") is True

    def test_chain_close_no_trigger(self) -> None:
        assert detect_chain_close("ещё подожду") is False
