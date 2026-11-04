"""Tests for MCP server functions and database operations with strict host isolation."""

import pytest
from pathlib import Path
from src.memory.db import RadarDatabase
from src.models import SourceType, TechRelease, UserStackProfile
from src.server import radar_record_feedback, radar_ingest_custom, radar_set_stack_profile


@pytest.fixture(autouse=True)
def isolate_storage(monkeypatch, tmp_path):
    """Ensure all tests use an isolated temporary storage directory, protecting ~/.adaptive-radar."""
    monkeypatch.setenv("RADAR_STORAGE_DIR", str(tmp_path))


def test_database_deduplication(tmp_path):
    db = RadarDatabase(tmp_path / "dedup.db")
    rel = TechRelease(
        release_id="gh:test/repo:v1",
        source_type=SourceType.GITHUB_RELEASE,
        project_or_repo="test/repo",
        version="v1",
        title="Test v1",
        body="Feature A",
        url="https://github.com/test/repo",
        published_at="2026-11-04T00:00:00Z",
        content_hash="hash123",
    )
    
    # First insert succeeds
    assert db.save_release(rel) is True
    # Duplicate hash fails
    assert db.save_release(rel) is False


def test_user_profile_crud(tmp_path):
    db = RadarDatabase(tmp_path / "profile.db")
    profile = UserStackProfile(
        keywords=["quant", "python"],
        preferred_tools=["pydantic", "sqlite"],
        banned_patterns=["eval"],
    )
    db.set_user_profile(profile)
    loaded = db.get_user_profile()
    assert "quant" in loaded.keywords
    assert "sqlite" in loaded.preferred_tools


def test_custom_ingest():
    res = radar_ingest_custom(
        title="LiteLLM v1.50: Prompt Caching",
        body="Added native prompt caching support for Anthropic and Gemini",
        source_url="https://github.com/BerriAI/litellm"
    )
    assert "Ingested custom release" in res


def test_record_feedback_prefix_cleaning(tmp_path):
    res = radar_record_feedback("atom:OpenAI Blog:abc12345", "ACCEPTED", "Great model updates")
    assert "Feedback recorded successfully" in res
    
    db = RadarDatabase(tmp_path / "radar.db")
    # Verify feedback was stored
    recent = db.get_recent_feedback(1)
    assert len(recent) == 1
    assert recent[0].project_or_repo == "OpenAI Blog"
