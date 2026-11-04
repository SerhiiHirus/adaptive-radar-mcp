"""Tests for ReleaseEvaluator and Safety policies."""

from adaptive_radar_mcp.evaluator.scoring import ReleaseEvaluator
from adaptive_radar_mcp.models import (
    DecisionType,
    FeedbackRecord,
    SourceType,
    TechRelease,
    UserStackProfile,
)


def test_evaluator_token_roi_and_context7():
    release = TechRelease(
        release_id="gh:pydantic/pydantic-ai:v2.65.0",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="pydantic/pydantic-ai",
        version="v2.65.0",
        title="PydanticAI v2.65.0 Released",
        body="Added dynamic thinking effort controls and native prompt caching for models.",
        url="https://github.com/pydantic/pydantic-ai",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_pydantic",
    )

    profile = UserStackProfile(
        keywords=["agents", "python", "fastapi"],
        preferred_tools=["pydantic", "fastapi"],
        banned_patterns=["eval"],
    )

    eval_result = ReleaseEvaluator.evaluate(release, profile)
    
    assert eval_result.score >= 7.0
    assert eval_result.recommended_action == "IMPLEMENT"
    assert "prompt caching" in eval_result.token_roi_summary
    assert eval_result.context7_query is not None
    assert "pydantic-ai" in eval_result.context7_query


def test_evaluator_banned_patterns():
    release = TechRelease(
        release_id="gh:unwanted/heavy-agent:v1",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="unwanted/heavy-agent",
        version="v1.0",
        title="Heavy Agent Framework",
        body="Includes heavy orchestration wrappers for simple scripts.",
        url="https://github.com/unwanted/heavy-agent",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_banned",
    )

    profile = UserStackProfile(
        keywords=["python"],
        preferred_tools=["pydantic"],
        banned_patterns=["heavy orchestration wrappers"],
    )

    eval_result = ReleaseEvaluator.evaluate(release, profile)
    assert eval_result.score <= 1.0
    assert eval_result.recommended_action == "IGNORE"
    assert "Matches banned pattern" in eval_result.rationale


def test_evaluator_eval_safe_mention():
    """Ensure mentioning eval metrics does NOT trigger false positive safety alert."""
    release = TechRelease(
        release_id="gh:metrics/evaluator:v1",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="metrics/evaluator",
        version="v1.0",
        title="Model Benchmark Suite",
        body="Improved accuracy on the MMLU eval dataset and benchmark scoring.",
        url="https://github.com/metrics/evaluator",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_safe_eval",
    )

    profile = UserStackProfile(keywords=["python", "benchmark"])
    eval_result = ReleaseEvaluator.evaluate(release, profile)
    assert eval_result.safety_verdict == "SAFE"
