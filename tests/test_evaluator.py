"""Tests for ReleaseEvaluator and Safety policies."""

from adaptive_radar_mcp.evaluator.scoring import ReleaseEvaluator
from adaptive_radar_mcp.models import (
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


def test_evaluator_semver_installed_version_diff():
    """Verify that SemVer comparison uses the actual installed version from user profile."""
    release = TechRelease(
        release_id="gh:pydantic/pydantic:v2.0.0",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="pydantic/pydantic",
        version="2.0.0",
        title="Pydantic V2 Release",
        body="Core rewrite with pydantic-core. Major architectural update with migration guide.",
        url="https://github.com/pydantic/pydantic",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_pydantic_v2",
    )

    profile = UserStackProfile(
        keywords=["validation", "models"],
        preferred_tools=["pydantic"],
        installed_packages={"pydantic": "1.10.2"},
    )

    eval_result = ReleaseEvaluator.evaluate(release, profile)
    assert "Installed: 1.10.2 -> Target: 2.0.0 (MAJOR)" in eval_result.rationale
    assert "[Migration Risk: HIGH]" in eval_result.rationale
    assert eval_result.context7_query == "pydantic migration guide 2.0.0"
    assert eval_result.resistance_level == "HIGH"


def test_least_resistance_policy_vetoes_breaking_core_rewrite():
    """Verify that breaking core rewrites are demoted to EXPLORE unless extraordinary ROI."""
    release = TechRelease(
        release_id="gh:some/library:v2.0.0",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="some/library",
        version="2.0.0",
        title="Major Core Rewrite v2.0",
        body="Complete breaking changes. Architectural rewrite of all interfaces and signatures.",
        url="https://github.com/some/library",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_breaking_v2",
    )

    profile = UserStackProfile(
        keywords=["agents", "python", "library"],
        preferred_tools=["library"],
        installed_packages={"library": "1.0.0"},
    )

    eval_result = ReleaseEvaluator.evaluate(release, profile)
    assert eval_result.resistance_level == "HIGH"
    assert eval_result.recommended_action == "EXPLORE"
    assert "Core rewrite VETOED" in eval_result.rationale


def test_least_resistance_policy_accepts_extraordinary_roi():
    """Verify that HIGH resistance is permitted for IMPLEMENT only if extraordinary 3x+ ROI benchmark."""
    release = TechRelease(
        release_id="gh:vendor/anthropic-client:v2.0.0",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="vendor/anthropic-client",
        version="2.0.0",
        title="v2.0.0 Anthropic Prompt Caching & Structured Output",
        body="Major release with Anthropic Prompt Caching (cache_control) and OpenAI Structured Outputs. Breaking changes to config.",
        url="https://github.com/vendor/anthropic-client",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_anthropic_v2",
    )

    profile = UserStackProfile(
        keywords=["prompt caching", "anthropic", "tokens", "structured outputs"],
        preferred_tools=["anthropic-client"],
        installed_packages={"anthropic-client": "1.5.0"},
    )

    eval_result = ReleaseEvaluator.evaluate(release, profile)
    assert eval_result.resistance_level == "HIGH"
    assert eval_result.score >= 8.0
    assert eval_result.recommended_action == "IMPLEMENT"
    assert "HIGH resistance accepted due to extraordinary 3x+ Token ROI" in eval_result.rationale


def test_least_resistance_policy_drop_in_low():
    """Verify that drop-in non-breaking updates are marked as LOW resistance."""
    release = TechRelease(
        release_id="gh:pkg/fast:v1.2.1",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="pkg/fast",
        version="1.2.1",
        title="Patch release",
        body="Bug fixes and minor performance improvements.",
        url="https://github.com/pkg/fast",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash_patch_121",
    )

    profile = UserStackProfile(
        keywords=["performance"],
        installed_packages={"fast": "1.2.0"},
    )

    eval_result = ReleaseEvaluator.evaluate(release, profile)
    assert eval_result.resistance_level == "LOW"
    assert "[Resistance: LOW (Drop-in / Config)]" in eval_result.rationale
