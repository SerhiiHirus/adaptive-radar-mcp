"""Tests for active learning and scoring bias."""

from adaptive_radar_mcp.memory.active_learning import ActiveLearningEngine
from adaptive_radar_mcp.models import DecisionType, FeedbackRecord


def test_active_learning_bias_calculation():
    history = [
        FeedbackRecord(
            release_id="gh:pydantic/pydantic-ai:v1",
            project_or_repo="pydantic/pydantic-ai",
            decision=DecisionType.ACCEPTED,
            reason="Great structured output support",
            timestamp="2026-11-04T00:00:00Z"
        ),
        FeedbackRecord(
            release_id="gh:bad/heavy-orchestrator:v1",
            project_or_repo="bad/heavy-orchestrator",
            decision=DecisionType.REJECTED,
            reason="Too heavy, unnecessary wrapper",
            timestamp="2026-11-04T00:00:00Z"
        )
    ]

    # Tool aligned with accepted history should receive positive bias
    bonus = ActiveLearningEngine.calculate_preference_bias("pydantic", "structured output engine", history)
    assert bonus > 0.0

    # Tool aligned with rejected history should receive penalty
    penalty = ActiveLearningEngine.calculate_preference_bias("heavy-orchestrator", "multi-agent wrapper", history)
    assert penalty < 0.0


def test_few_shot_prompt_generation():
    history = [
        FeedbackRecord(
            release_id="gh:pydantic:v1",
            project_or_repo="pydantic",
            decision=DecisionType.ACCEPTED,
            reason="Native type validation",
            timestamp="2026-11-04T00:00:00Z"
        )
    ]
    few_shot = ActiveLearningEngine.build_few_shot_context(history)
    assert "Active Learning Few-Shot" in few_shot
    assert "ACCEPTED" in few_shot
    assert "Native type validation" in few_shot
