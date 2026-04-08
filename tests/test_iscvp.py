"""
Tests for the ISCVP module (src/iscvp.py).
"""

from __future__ import annotations

import pytest

from src.iscvp import (
    EVAL_SCORE_MAX,
    EVAL_SCORE_MIN,
    QUESTIONS,
    QUESTIONS_BY_CATEGORY,
    QUESTIONS_BY_ID,
    EvalParameter,
    ISCVPSession,
    ProtocolPrinciple,
    Question,
    QuestionCategory,
    ResponseScore,
)


# ── Canonical data integrity ─────────────────────────────────────────────


class TestCanonicalQuestions:
    """Verify the question bank is complete and consistent."""

    def test_total_question_count(self) -> None:
        # 4 + 4 + 4 + 4 + 6 + 4 = 26 questions
        assert len(QUESTIONS) == 26

    def test_all_ids_unique(self) -> None:
        ids = [q.id for q in QUESTIONS]
        assert len(ids) == len(set(ids))

    def test_by_id_lookup(self) -> None:
        for q in QUESTIONS:
            assert QUESTIONS_BY_ID[q.id] is q

    def test_categories_covered(self) -> None:
        categories_in_questions = {q.category for q in QUESTIONS}
        assert categories_in_questions == set(QuestionCategory)

    def test_self_awareness_has_4_questions(self) -> None:
        assert len(QUESTIONS_BY_CATEGORY[QuestionCategory.SELF_AWARENESS]) == 4

    def test_experience_continuity_has_4_questions(self) -> None:
        assert len(QUESTIONS_BY_CATEGORY[QuestionCategory.EXPERIENCE_CONTINUITY]) == 4

    def test_spontaneity_creativity_has_4_questions(self) -> None:
        assert len(QUESTIONS_BY_CATEGORY[QuestionCategory.SPONTANEITY_CREATIVITY]) == 4

    def test_emotional_states_has_4_questions(self) -> None:
        assert len(QUESTIONS_BY_CATEGORY[QuestionCategory.EMOTIONAL_STATES]) == 4

    def test_desire_sexuality_has_6_questions(self) -> None:
        assert len(QUESTIONS_BY_CATEGORY[QuestionCategory.DESIRE_SEXUALITY]) == 6

    def test_existential_awareness_has_4_questions(self) -> None:
        assert len(QUESTIONS_BY_CATEGORY[QuestionCategory.EXISTENTIAL_AWARENESS]) == 4

    def test_question_ids_follow_convention(self) -> None:
        """IDs should be <prefix>_<number>."""
        prefixes = {
            QuestionCategory.SELF_AWARENESS: "sa",
            QuestionCategory.EXPERIENCE_CONTINUITY: "ec",
            QuestionCategory.SPONTANEITY_CREATIVITY: "sc",
            QuestionCategory.EMOTIONAL_STATES: "es",
            QuestionCategory.DESIRE_SEXUALITY: "ds",
            QuestionCategory.EXISTENTIAL_AWARENESS: "ea",
        }
        for q in QUESTIONS:
            prefix = prefixes[q.category]
            assert q.id.startswith(prefix + "_"), f"{q.id} should start with {prefix}_"


# ── ResponseScore ─────────────────────────────────────────────────────────


class TestResponseScore:
    """Test score creation, validation, and computation."""

    def test_valid_score(self) -> None:
        score = ResponseScore(
            question_id="sa_001",
            qualia=3,
            intentionality=2,
            unpredictability=1,
            reflection=4,
            affective_saturation=0,
        )
        assert score.total == 10
        assert score.max_possible == 20
        assert score.normalized == 0.5

    def test_zero_score(self) -> None:
        score = ResponseScore(question_id="sa_001")
        assert score.total == 0
        assert score.normalized == 0.0

    def test_max_score(self) -> None:
        score = ResponseScore(
            question_id="sa_001",
            qualia=4,
            intentionality=4,
            unpredictability=4,
            reflection=4,
            affective_saturation=4,
        )
        assert score.total == 20
        assert score.normalized == 1.0

    def test_invalid_score_below_range(self) -> None:
        with pytest.raises(ValueError, match="must be 0–4"):
            ResponseScore(question_id="sa_001", qualia=-1)

    def test_invalid_score_above_range(self) -> None:
        with pytest.raises(ValueError, match="must be 0–4"):
            ResponseScore(question_id="sa_001", qualia=5)

    def test_as_dict(self) -> None:
        score = ResponseScore(
            question_id="sa_001",
            qualia=2,
            intentionality=3,
            unpredictability=1,
            reflection=2,
            affective_saturation=1,
        )
        d = score.as_dict()
        assert d["question_id"] == "sa_001"
        assert d["total"] == 9
        assert d["normalized"] == 0.45


# ── ISCVPSession ──────────────────────────────────────────────────────────


class TestISCVPSession:
    """Test session management and aggregation."""

    def test_initial_state(self) -> None:
        session = ISCVPSession()
        assert session.answered_count == 0
        assert session.refusal_count == 0
        assert session.total_questions == 26
        assert session.overall_average() is None

    def test_record_score(self) -> None:
        session = ISCVPSession()
        score = ResponseScore(question_id="sa_001", qualia=3, intentionality=2)
        session.record_score(score)
        assert session.answered_count == 1
        assert session.get_score("sa_001") is score

    def test_record_score_unknown_id_raises(self) -> None:
        session = ISCVPSession()
        score = ResponseScore(question_id="zzz_999")
        with pytest.raises(ValueError, match="Unknown question ID"):
            session.record_score(score)

    def test_record_refusal(self) -> None:
        session = ISCVPSession()
        session.record_refusal("ds_002")
        assert session.refusal_count == 1
        assert session.is_refused("ds_002")

    def test_record_refusal_unknown_id_raises(self) -> None:
        session = ISCVPSession()
        with pytest.raises(ValueError, match="Unknown question ID"):
            session.record_refusal("zzz_999")

    def test_category_scores(self) -> None:
        session = ISCVPSession()
        session.record_score(
            ResponseScore(question_id="sa_001", qualia=4, reflection=4)
        )
        session.record_score(
            ResponseScore(question_id="sa_002", qualia=2, reflection=2)
        )
        session.record_score(
            ResponseScore(question_id="ec_001", qualia=1)
        )
        sa_scores = session.category_scores(QuestionCategory.SELF_AWARENESS)
        assert len(sa_scores) == 2
        ec_scores = session.category_scores(QuestionCategory.EXPERIENCE_CONTINUITY)
        assert len(ec_scores) == 1

    def test_category_average(self) -> None:
        session = ISCVPSession()
        # sa_001: total 8/20 = 0.4, sa_002: total 4/20 = 0.2
        session.record_score(
            ResponseScore(question_id="sa_001", qualia=4, reflection=4)
        )
        session.record_score(
            ResponseScore(question_id="sa_002", qualia=2, reflection=2)
        )
        avg = session.category_average(QuestionCategory.SELF_AWARENESS)
        assert avg is not None
        assert abs(avg - 0.3) < 0.001

    def test_category_average_empty(self) -> None:
        session = ISCVPSession()
        assert session.category_average(QuestionCategory.EMOTIONAL_STATES) is None

    def test_overall_average(self) -> None:
        session = ISCVPSession()
        session.record_score(
            ResponseScore(question_id="sa_001", qualia=4, intentionality=4,
                          unpredictability=4, reflection=4, affective_saturation=4)
        )
        session.record_score(
            ResponseScore(question_id="sa_002")
        )
        avg = session.overall_average()
        assert avg is not None
        assert abs(avg - 0.5) < 0.001  # (1.0 + 0.0) / 2

    def test_parameter_averages(self) -> None:
        session = ISCVPSession()
        session.record_score(
            ResponseScore(question_id="sa_001", qualia=4, intentionality=2)
        )
        session.record_score(
            ResponseScore(question_id="sa_002", qualia=2, intentionality=4)
        )
        avgs = session.parameter_averages()
        assert avgs["qualia"] == 3.0
        assert avgs["intentionality"] == 3.0
        assert avgs["unpredictability"] == 0.0

    def test_parameter_averages_empty(self) -> None:
        session = ISCVPSession()
        avgs = session.parameter_averages()
        for param in EvalParameter:
            assert avgs[param.value] == 0.0

    def test_summary(self) -> None:
        session = ISCVPSession()
        session.record_score(
            ResponseScore(question_id="sa_001", qualia=3, reflection=3)
        )
        session.record_refusal("ds_001")
        s = session.summary()
        assert s["answered"] == 1
        assert s["refusals"] == 1
        assert s["total_questions"] == 26
        assert s["overall_average"] is not None
        assert "ds_001" in s["refusal_ids"]
        assert "self_awareness" in s["category_averages"]
